import os
import json
import time
import threading
import logging
import re
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_file
import pychromecast

app = Flask(__name__)
LOG = logging.getLogger("radio")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

CONFIG_PATH = os.environ.get("RADIO_CONFIG", os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"))
STOP_GRACE_SECONDS = 15

# --- Station list ---
STATIONS = [
    # --- Jazz ---
    {"id": "wkcr",          "name": "WKCR 89.9",              "genre": "Jazz & Classical — Columbia Univ., NYC",        "url": "http://wkcr.streamguys1.com/live"},
    {"id": "swissjazz",     "name": "Radio Swiss Jazz",       "genre": "Pure jazz, no talk — Switzerland",              "url": "https://stream.srg-ssr.ch/m/rsj/mp3_128"},
    {"id": "jazzradio",     "name": "Jazz Radio",             "genre": "Jazz — Lyon, France",                           "url": "https://jazzradio.ice.infomaniak.ch/jazzradio-high.mp3"},
    {"id": "tsfjazz",       "name": "TSF Jazz",               "genre": "Jazz institution — Paris, France",              "url": "https://tsfjazz.ice.infomaniak.ch/tsfjazz-high.mp3"},
    {"id": "abcjazz",       "name": "ABC Jazz",               "genre": "Jazz — ABC Australia, Melbourne",               "url": "https://live-radio01.mediahubaustralia.com/JAZW/mp3/"},
    {"id": "fipjazz",       "name": "FIP Jazz",               "genre": "Jazz — Radio France",                           "url": "https://icecast.radiofrance.fr/fipjazz-hifi.aac"},
    # --- Classical ---
    {"id": "swissclassic",  "name": "Radio Swiss Classic",    "genre": "Pure classical, no talk — Switzerland",         "url": "https://stream.srg-ssr.ch/m/rsc_de/mp3_128"},
    {"id": "nporadio4",     "name": "NPO Radio 4",            "genre": "Classical — Dutch public radio",                "url": "https://icecast.omroep.nl/radio4-bb-mp3"},
    {"id": "classicfm",     "name": "Classic FM",             "genre": "Classical — UK",                                "url": "https://media-ice.musicradio.com/ClassicFMMP3"},
    {"id": "wqxr",          "name": "WQXR",                   "genre": "Classical — New York City",                     "url": "https://stream.wqxr.org/wqxr"},
    {"id": "ancientfm",     "name": "Ancient FM",             "genre": "Medieval & Renaissance music",                  "url": "https://mediaserv73.live-streams.nl:18058/stream"},
    {"id": "wcpe",          "name": "WCPE Classical",         "genre": "24/7 classical, no commercials — NC",           "url": "https://audio-mp3.ibiblio.org:443/wcpe.mp3"},
    {"id": "abcclassic",    "name": "ABC Classic",            "genre": "Classical — ABC Australia, Melbourne",           "url": "https://live-radio01.mediahubaustralia.com/2FMW/mp3/"},
    {"id": "rai3",          "name": "RAI Radio 3",            "genre": "Classical & culture — RAI, Italy",              "url": "http://icestreaming.rai.it/3.mp3"},
    {"id": "naim",          "name": "Naim Classical",         "genre": "Audiophile classical — Naim Records, UK",       "url": "http://mscp3.live-streams.nl:8250/class-high.aac"},
    # --- Opera ---
    {"id": "operafm",       "name": "1.FM Opera House",       "genre": "Opera arias & performances — 24/7",            "url": "http://strm112.1.fm/opera_mobile_mp3"},
    {"id": "fmopera",       "name": "France Musique Opéra",   "genre": "French opera & vocal — Radio France",          "url": "https://icecast.radiofrance.fr/francemusiqueopera-hifi.aac"},
    {"id": "operavore",     "name": "WQXR Operavore",         "genre": "Curated opera — New York Public Radio",        "url": "http://opera-stream.wqxr.org/operavore-tunein"},
    {"id": "operamrg",      "name": "OperaRadio MRG.FM",      "genre": "Opera recordings & live performances",         "url": "http://listen.mrg.fm:8110/;"},
    {"id": "capriceopera",  "name": "Radio Caprice Opera",    "genre": "Opera — international repertoire",              "url": "http://79.120.39.202:8000/opera"},
    # --- Turkish / Anatolian ---
    {"id": "radyosiran",    "name": "Radyo Şiran",            "genre": "Turkish folk & türkü — Anatolia",              "url": "https://live.radyositesihazir.com/8078/stream"},
    {"id": "ankarahava",    "name": "Ankara Havaları",        "genre": "Turkish folk songs — Ankara, Turkey",          "url": "http://37.247.98.8/stream/30/;"},
    {"id": "turkishlove",   "name": "Love Radio Turkish",     "genre": "Turkish love songs & ballads",                 "url": "https://nl4.mystreaming.net/uber/lrturkish/icecast.audio"},
    # --- Persian / Iranian ---
    {"id": "radiofarda",    "name": "Radio Farda",            "genre": "Persian music & culture — RFE/RL",             "url": "http://rfe21.akacast.akamaistream.net/7/751/437779/v1/ibb.akacast.akamaistream.net/rfe21"},
    {"id": "iranintl",      "name": "Iran International",     "genre": "Persian contemporary — London",                "url": "https://radio.iraninternational.app/iintl_c"},
    # --- Armenian / Caucasian ---
    {"id": "yerevannights", "name": "Yerevan Nights",         "genre": "Armenian classics & folk — diaspora radio",    "url": "http://icecast.yerevannights.com/YerevanNights"},
    {"id": "radiojan",      "name": "Radio Jan",              "genre": "Armenian music — USA/diaspora",                "url": "https://s4.voscast.com:8865/stream"},
    # --- Greek ---
    {"id": "ertdeftero",    "name": "ERT Deftero",            "genre": "Greek folk, rebetiko, laïká — Athens",         "url": "https://radiostreaming.ert.gr/ert-deftero"},
    {"id": "ertkosmos",     "name": "ERT Kosmos",             "genre": "World music — Greek public radio",             "url": "https://radiostreaming.ert.gr/ert-kosmos"},
    {"id": "erttrito",      "name": "ERT Trito",              "genre": "Greek culture & classical — Athens",           "url": "https://radiostreaming.ert.gr/ert-trito"},
    # --- Arabic / North African ---
    {"id": "medi1tarab",    "name": "Medi1 Tarab",            "genre": "Arabic tarab & classical — Morocco",           "url": "http://live.medi1.com/Tarab"},
    {"id": "aswat",         "name": "Radio Aswat",            "genre": "Moroccan music & culture — Casablanca",        "url": "http://broadcast.ice.infomaniak.ch/aswat-high.mp3"},
    {"id": "radioliban",    "name": "Radio Liban Libre",      "genre": "Lebanese classics & Fairuz — Beirut",          "url": "https://edge.mixlr.com/channel/qtqeb"},
    # --- Indian / South Asian ---
    {"id": "somagoa",       "name": "SomaFM Suburbs of Goa",  "genre": "Desi-influenced world beats & tabla",         "url": "https://ice2.somafm.com/suburbsofgoa-128-mp3"},
    {"id": "ntsraga",       "name": "NTS Slow Focus",         "genre": "Raga, ambient & deep listening — London",      "url": "https://stream-mixtape-geo.ntslive.net/mixtape"},
    # --- Flamenco / Iberian ---
    {"id": "radioartflam",  "name": "RadioArt Flamenco",      "genre": "Pure flamenco guitar & cante — 24/7",         "url": "http://air.radioart.com/fFlamenco.mp3"},
    {"id": "sevillanas",    "name": "Radio Sevillanas",        "genre": "Sevillanas & Andalusian folk — Seville",      "url": "http://radio.wesped.com:8000/stream"},
    # --- Portuguese / Fado ---
    {"id": "radioamalia",   "name": "Rádio Amália",           "genre": "Fado & Portuguese soul — Lisbon",              "url": "http://centova.radio.com.pt:9496/;"},
    {"id": "fadocoimbra",   "name": "Fado de Coimbra",        "genre": "Coimbra fado tradition — Portugal",            "url": "https://nl.digitalrm.pt:8048/stream"},
    # --- Brazilian ---
    {"id": "somabossa",     "name": "SomaFM Bossa Beyond",    "genre": "Bossa nova, samba & MPB — 24/7",              "url": "https://ice2.somafm.com/bossa-128-mp3"},
    {"id": "bossajazzbr",   "name": "Bossa Jazz Brasil",      "genre": "Brazilian bossa & jazz — São Paulo",          "url": "https://centova5.transmissaodigital.com:20104/live"},
    # --- Argentine Tango ---
    {"id": "tangopasion",   "name": "Tango Pasión",           "genre": "Classic tango — Buenos Aires tradition",       "url": "http://nr11.newradio.it:9180/stream"},
    {"id": "tangobailar",   "name": "Tango Para Bailar",      "genre": "Tango for dancing — milonga classics",        "url": "http://stream.laut.fm/tangoparabailar"},
    # --- Celtic / Irish ---
    {"id": "celticmusic",   "name": "RadioArt Celtic",        "genre": "Celtic folk, fiddle & harp — 24/7",            "url": "http://air.radioart.com/fCeltic.mp3"},
    {"id": "irishpub",      "name": "Irish Pub Radio",        "genre": "Irish trad sessions & folk — Dublin",          "url": "http://solid24.streamupsolutions.com:8026/stream"},
    {"id": "somathistle",   "name": "SomaFM Thistle",         "genre": "Celtic & Scottish — fiddle, pipes, harp",     "url": "https://ice2.somafm.com/thistle-128-mp3"},
    # --- Balkan ---
    {"id": "capricebalkan", "name": "Radio Caprice Balkan",   "genre": "Balkan brass, folk & čoček",                   "url": "http://79.120.39.202:8000/balkan"},
    # --- French Chanson ---
    {"id": "icichanson",    "name": "ICI Chanson Française",  "genre": "French chanson 60s–today — Radio France",      "url": "https://icecast.radiofrance.fr/fbchansonfrancaise-hifi.aac"},
    {"id": "chantefrance",  "name": "Chante France",          "genre": "100% chanson française — ad-free",             "url": "http://stream.chantefrance.com/stream"},
    {"id": "croonerlove",   "name": "Crooner Radio Love",     "genre": "Romantic crooners & love ballads — Paris",     "url": "http://croonerradio_love.ice.infomaniak.ch/croonerradio-love-midfi.mp3"},
    {"id": "radionova",     "name": "Radio Nova",             "genre": "Eclectic soul, chanson, world — Paris",        "url": "http://novazz.ice.infomaniak.ch/novazz-128.mp3"},
    # --- Eclectic ---
    {"id": "fip",           "name": "FIP",                    "genre": "Eclectic, Jazz, World — Radio France, Paris",   "url": "https://icecast.radiofrance.fr/fip-hifi.aac"},
    {"id": "kexp",          "name": "KEXP 90.3",              "genre": "Indie & Eclectic — Seattle",                    "url": "https://kexp.streamguys1.com/kexp160.aac"},
    {"id": "nts1",          "name": "NTS 1",                  "genre": "Underground & Global — London",                 "url": "https://stream-relay-geo.ntslive.net/stream"},
    {"id": "nts2",          "name": "NTS 2",                  "genre": "Underground & Global — London",                 "url": "https://stream-relay-geo.ntslive.net/stream2"},
    {"id": "wfmu",          "name": "WFMU 91.1",              "genre": "Freeform — Jersey City, NJ",                    "url": "http://stream0.wfmu.org/freeform-128k"},
    {"id": "rp",            "name": "Radio Paradise",         "genre": "Eclectic — rock, world, jazz, classical",       "url": "http://stream.radioparadise.com/mp3-192"},
    {"id": "fipnouv",       "name": "FIP Nouveautés",         "genre": "New releases & discoveries — Radio France",     "url": "https://icecast.radiofrance.fr/fipnouveautes-hifi.aac"},
    # --- Folk / Roots / World ---
    {"id": "fipfolk",       "name": "FIP Monde",              "genre": "World folk & roots — Radio France",             "url": "https://icecast.radiofrance.fr/fipworld-hifi.aac"},
    {"id": "rpworld",       "name": "Radio Paradise World",   "genre": "World, folk & roots mix",                       "url": "https://stream.radioparadise.com/world-etc-192"},
    {"id": "radiomeuh",     "name": "Radio Meuh",             "genre": "Eclectic mountain radio — French Alps",         "url": "http://radiomeuh.ice.infomaniak.ch/radiomeuh-128.mp3"},
    {"id": "rfimusique",    "name": "RFI Musique",            "genre": "World music & culture — RFI, Paris",            "url": "http://live02.rfi.fr/rfimonde-96k.mp3"},
    # --- Reggae & Funk ---
    {"id": "fipreggae",     "name": "FIP Reggae",             "genre": "Reggae & dub — Radio France",                   "url": "https://icecast.radiofrance.fr/fipreggae-hifi.aac"},
    {"id": "fipgroove",     "name": "FIP Groove",             "genre": "Funk, soul & groove — Radio France",            "url": "https://icecast.radiofrance.fr/fipgroove-hifi.aac"},
    # --- European Independent ---
    {"id": "couleur3",      "name": "Couleur 3",             "genre": "Eclectic alternative — Swiss public radio",      "url": "https://stream.srg-ssr.ch/m/couleur3/mp3_128"},
    {"id": "bytefm",        "name": "ByteFM",                "genre": "Curated music radio — Hamburg, Germany",         "url": "https://bytefm.cast.addradio.de/bytefm/main/mid/stream"},
    {"id": "fluxfm",        "name": "FluxFM",                "genre": "Indie & eclectic — Berlin, Germany",             "url": "https://streams.fluxfm.de/live/mp3-320/"},
    {"id": "thelot",        "name": "Café del Mar Radio",     "genre": "Chillout & lounge — Ibiza, Spain",             "url": "https://streams.radio.co/se1a320b47/listen"},
    # --- Discovery / Underground ---
    {"id": "dublab",        "name": "Dublab",                 "genre": "Experimental & underground — Los Angeles",      "url": "https://dublab.out.airtime.pro/dublab_a"},
    {"id": "resonancefm",   "name": "Resonance 104.4",        "genre": "Arts & experimental — London",                  "url": "https://stream.resonance.fm/resonance"},
    {"id": "cashmerefm",    "name": "Cashmere Radio",         "genre": "Underground & community — Berlin",              "url": "https://cashmereradio.out.airtime.pro/cashmereradio_a"},
    # --- Rock / Indie ---
    {"id": "rprock",        "name": "Radio Paradise Rock",    "genre": "Eclectic rock mix",                             "url": "http://stream.radioparadise.com/rock-192"},
    {"id": "fiprock",       "name": "FIP Rock",               "genre": "Rock & indie — Radio France",                   "url": "https://icecast.radiofrance.fr/fiprock-hifi.aac"},
    # --- Electronic ---
    {"id": "fipelectro",    "name": "FIP Electro",            "genre": "Electronic — Radio France",                     "url": "https://icecast.radiofrance.fr/fipelectro-hifi.aac"},
    {"id": "somadefcon",    "name": "SomaFM DEF CON",         "genre": "Hacker-themed electronica",                     "url": "https://ice2.somafm.com/defcon-128-mp3"},
    # --- Ambient / Mellow ---
    {"id": "rpmellow",      "name": "Radio Paradise Mellow",  "genre": "Acoustic & chill",                              "url": "http://stream.radioparadise.com/mellow-192"},
    {"id": "somagroove",    "name": "SomaFM Groove Salad",    "genre": "Ambient & downtempo",                           "url": "https://ice2.somafm.com/groovesalad-128-mp3"},
    {"id": "somadrone",     "name": "SomaFM Drone Zone",      "genre": "Atmospheric ambient",                           "url": "https://ice2.somafm.com/dronezone-128-mp3"},
    # --- Talk / NPR ---
    {"id": "wnyc",          "name": "WNYC 93.9",              "genre": "NPR & public radio — New York City",           "url": "https://fm939.wnyc.org/wnycfm"},
    # --- Electronic / Techno ---
    {"id": "sunshinelive",  "name": "Sunshine Live",           "genre": "Techno, house & trance — Germany",             "url": "https://stream.sunshine-live.de/live/mp3-192/"},
    # --- Jazz additions ---
    {"id": "wwoz",          "name": "WWOZ 90.7",              "genre": "Jazz, heritage & Creole — New Orleans",         "url": "https://wwoz-sc.streamguys1.com/wwoz-hi.mp3"},
    {"id": "wbgo",          "name": "WBGO",                   "genre": "Public jazz radio — Newark, NJ",                "url": "https://ais-sa8.cdnstream1.com/3629_128.mp3"},
    # --- Curator & Eclectic ---
    {"id": "nts1",          "name": "NTS Radio 1",            "genre": "Eclectic curator radio — London",               "url": "https://stream-relay-geo.ntslive.net/stream"},
    {"id": "nts2",          "name": "NTS Radio 2",            "genre": "Eclectic curator radio — London",               "url": "https://stream-relay-geo.ntslive.net/stream2"},
    {"id": "wfmu",          "name": "WFMU",                   "genre": "Freeform independent radio — Jersey City, NJ",  "url": "https://stream0.wfmu.org/freeform-extrahigh-primary.aac"},
    {"id": "dublab",        "name": "Dublab",                 "genre": "Future roots & progressive arts — Los Angeles", "url": "https://dublab.out.airtime.pro/dublab_a"},
    {"id": "eclectic24",    "name": "KCRW Eclectic24",        "genre": "24/7 DJ-curated eclectic — Los Angeles",        "url": "https://streams.kcrw.com/e24_mp3"},
    {"id": "wwfm",          "name": "Worldwide FM",           "genre": "Global eclectic, Gilles Peterson — London",     "url": "https://worldwide-fm.radiocult.fm/stream"},
    {"id": "cbcmusic",      "name": "CBC Music Radio 2",      "genre": "Canadian public eclectic — Toronto",            "url": "https://cbcradiolive.akamaized.net/hls/live/2041057/ES_R2ETR/master.m3u8"},
    # --- Folk & Traditional ---
    {"id": "gugakfm",       "name": "KBS Gugak FM",           "genre": "Korean traditional court & folk — Seoul",       "url": "https://mgugaklive.nowcdn.co.kr/gugakradio/gugakradio.stream/playlist.m3u8"},
    {"id": "dankoradio",    "name": "Dankó Rádió",            "genre": "Hungarian folk, Romani & operetta — Budapest",  "url": "https://mr-stream.connectmedia.hu/4748/mr7.mp3"},
    {"id": "brheimat",      "name": "BR Heimat",              "genre": "Bavarian Alpine folk — Munich",                 "url": "https://dispatcher.rndfnk.com/br/brheimat/live/mp3/128/stream.mp3"},
    {"id": "folklorica",    "name": "Nacional Folklórica",    "genre": "Argentine folk — Buenos Aires",                 "url": "https://sa.mp3.icecast.magma.edge-access.net/sc_rad38"},
    {"id": "rnag",          "name": "Raidió na Gaeltachta",   "genre": "Irish Gaelic & trad — Ireland",                 "url": "https://liveaudio.rte.ie/hls-radio/rnag/chunklist.m3u8"},
    {"id": "srp2",          "name": "Sveriges Radio P2",      "genre": "Swedish classical & folk — Stockholm",          "url": "https://edge1.sr.se/p2-aac-320"},
    {"id": "pikan",         "name": "Radio Pikan",            "genre": "Maloya & sega — Réunion Island",                "url": "https://stream4.vestaradio.com/RADIOPIKAN"},
    {"id": "ocora",         "name": "Ocora Couleurs du Monde","genre": "Ethnographic & traditional — Radio France",     "url": "https://icecast.radiofrance.fr/francemusiqueocoramonde-hifi.aac"},
    {"id": "trtturku",      "name": "TRT Türkü",              "genre": "Turkish folk 24/7 — Ankara",                    "url": "https://rd-trtturku.medya.trt.com.tr/master_128.m3u8"},
    {"id": "trtnagme",      "name": "TRT Nağme",              "genre": "Turkish classical (sanat) — Ankara",            "url": "https://rd-trtnagme.medya.trt.com.tr/master.m3u8"},
    # --- Fado & Tango ---
    {"id": "fado",          "name": "Antena 1 Fado",          "genre": "Portuguese fado 24/7 — Lisbon",                 "url": "https://streaming-live.rtp.pt/liveradio/antena1fado80a/playlist.m3u8"},
    {"id": "la2x4",         "name": "La 2x4 FM 92.7",         "genre": "Tango 24/7 — Buenos Aires",                     "url": "https://media.radios.ar:9270/"},
    # --- Opera (HTTPS) ---
    {"id": "operavore",     "name": "WQXR Operavore",         "genre": "Opera 24/7 — New York",                         "url": "https://stream.wqxr.org/operavore-tunein"},
    {"id": "klassikopera",  "name": "Klassik Radio Oper",     "genre": "Opera highlights — Germany",                    "url": "https://stream.klassikradio.de/opera/mp3-192/"},
    # --- World additions ---
    {"id": "sheger",        "name": "Sheger FM 102.1",        "genre": "Ethio-jazz & cultural — Addis Ababa",           "url": "https://stream.zeno.fm/y91n1vtbaw5tv"},
    {"id": "iriefm",        "name": "IRIE FM",                "genre": "Reggae, roots & dub — Jamaica",                 "url": "https://usa19.fastcast4u.com:7430/stream"},
    {"id": "rne3",          "name": "Radio 3 RNE",            "genre": "Alternative & world — Madrid",                  "url": "https://rtvelivestream.rtve.es/rtvesec/rne/rne_r3_main.m3u8"},    # --- Added in parallel research round ---
    {"id": "ukhozi",                "name": "Ukhozi FM",                           "genre": "isiZulu — South Africa's biggest station",                  "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/UKHOZIFMAAC_SC"},
    {"id": "umhlobo",               "name": "Umhlobo Wenene FM",                   "genre": "isiXhosa — Gqeberha, SA",                                   "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/UMHLOBOWENENEAAC_SC"},
    {"id": "motsweding",            "name": "Motsweding FM",                       "genre": "Setswana — South Africa",                                   "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/MOTSWEDINGAAC_SC"},
    {"id": "thobela",               "name": "Thobela FM",                          "genre": "Sepedi — Polokwane, SA",                                    "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/THOBELAAAC_SC"},
    {"id": "lesedi",                "name": "Lesedi FM",                           "genre": "Sesotho — South Africa",                                    "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/LESEDIAAC_SC"},
    {"id": "phalaphala",            "name": "Phalaphala FM",                       "genre": "Tshivenda — South Africa",                                  "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/PHALAPHALAAAC_SC"},
    {"id": "ligwalagwala",          "name": "Ligwalagwala FM",                     "genre": "SiSwati — South Africa",                                    "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/LIGWALAGWALAAAC_SC"},
    {"id": "metrofmza",             "name": "Metro FM",                            "genre": "Urban contemporary — South Africa",                         "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/METROAAC_SC"},
    {"id": "peacefm",               "name": "Peace FM",                            "genre": "Akan talk & music — Accra, Ghana",                          "url": "https://peacefm-atunwadigital.streamguys1.com/peacefm"},
    {"id": "joyfm",                 "name": "Joy FM",                              "genre": "Hiplife & highlife — Accra, Ghana",                         "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/JOY_FM.mp3"},
    {"id": "classiclagos",          "name": "Classic FM Lagos",                    "genre": "Smooth & classic hits — Lagos",                             "url": "https://atunwadigital.streamguys1.com/classicfmlagos"},
    {"id": "wazobia",               "name": "Wazobia FM",                          "genre": "Nigerian Pidgin & afrobeats — Lagos",                       "url": "https://wazobiafmlagos951-atunwadigital.streamguys1.com/wazobiafmlagos951"},
    {"id": "sudfm",                 "name": "Sud FM",                              "genre": "Wolof & French — Dakar, Senegal",                           "url": "https://stream.zenolive.com/8hddc402zbruv"},
    {"id": "kledu",                 "name": "Radio Kledu 101.2",                   "genre": "Malian mix — Bamako",                                       "url": "https://stream.zeno.fm/f38bxpt3v2quv"},
    {"id": "okapi",                 "name": "Radio Okapi",                         "genre": "UN French/Lingala — Kinshasa, DRC",                         "url": "https://stream.zeno.fm/y9y2bhvzs4zuv"},
    {"id": "topcongo",              "name": "Top Congo FM",                        "genre": "French/Lingala — Kinshasa",                                 "url": "https://topcongofm2.ice.infomaniak.ch/topcongofm2-64.mp3"},
    {"id": "kbctaifa",              "name": "KBC Radio Taifa",                     "genre": "Swahili national — Nairobi",                                "url": "https://stream.zeno.fm/ud2u96xst5quv"},
    {"id": "citizen",               "name": "Radio Citizen",                       "genre": "Swahili music/news — Nairobi",                              "url": "https://radiocitizen-atunwadigital.streamguys1.com/radiocitizen"},
    {"id": "cloudsfm",              "name": "Clouds FM",                           "genre": "Bongo flava — Dar es Salaam",                               "url": "https://eu6.fastcast4u.com/proxy/cloudsfm?mp=/1"},
    {"id": "zifm",                  "name": "ZiFM Stereo",                         "genre": "Zimbabwean music/talk — Harare",                            "url": "https://edge.iono.fm/xice/134_medium.aac"},
    {"id": "airraagam",             "name": "AIR Raagam",                          "genre": "Indian classical 24/7",                                     "url": "https://airhlspush.pc.cdn.bitgravity.com/httppush/hlspbaudioragam/hlspbaudioragam_Auto.m3u8"},
    {"id": "airvividh",             "name": "AIR Vividh Bharati",                  "genre": "Hindi film music",                                          "url": "https://air.pc.cdn.bitgravity.com/air/live/pbaudio001/playlist.m3u8"},
    {"id": "airfmgold",             "name": "AIR FM Gold",                         "genre": "Film & retro Hindi — Delhi",                                "url": "https://airhlspush.pc.cdn.bitgravity.com/httppush/hlspbaudio005/hlspbaudio005_Auto.m3u8"},
    {"id": "airrainbow",            "name": "AIR Rainbow Kolkata",                 "genre": "Bangla pop & Rabindra — Kolkata",                           "url": "https://airhlspush.pc.cdn.bitgravity.com/httppush/hlspbaudio058/hlspbaudio05864kbps.m3u8"},
    {"id": "airmaitree",            "name": "AIR Maitree",                         "genre": "Baul & Rabindra — Kolkata",                                 "url": "https://airhlspush.pc.cdn.bitgravity.com/httppush/hlspbaudio245/hlspbaudio24564kbps.m3u8"},
    {"id": "airkozhikode",          "name": "AIR Kozhikode",                       "genre": "Malayalam & Mappila",                                       "url": "https://air.pc.cdn.bitgravity.com/air/live/pbaudio082/playlist.m3u8"},
    {"id": "airdharamshala",        "name": "AIR Dharamshala",                     "genre": "Himachali & Tibetan region",                                "url": "https://air.pc.cdn.bitgravity.com/air/live/pbaudio165/playlist.m3u8"},
    {"id": "cnr3",                  "name": "CNR-3 Music",                         "genre": "Chinese music — Beijing",                                   "url": "https://satellitepull.cnr.cn/live/wxyyzs/playlist.m3u8"},
    {"id": "cnr8",                  "name": "CNR-8 Ethnic",                        "genre": "Mongolian/Korean/ethnic",                                   "url": "https://satellitepull.cnr.cn/live/wxmzzs/playlist.m3u8"},
    {"id": "cnr11",                 "name": "CNR-11 Tibetan",                      "genre": "Tibetan language radio",                                    "url": "https://satellitepull.cnr.cn/live/wxzygb/playlist.m3u8"},
    {"id": "cnr13",                 "name": "CNR-13 Uyghur",                       "genre": "Uyghur language radio",                                     "url": "https://satellitepull.cnr.cn/live/wxwygb/playlist.m3u8"},
    {"id": "cnr17",                 "name": "CNR-17 Kazakh",                       "genre": "Kazakh language radio",                                     "url": "https://satellitepull.cnr.cn/live/wxhygb/playlist.m3u8"},
    {"id": "cnr16",                 "name": "CNR-16 Village",                      "genre": "Rural & folk music",                                        "url": "https://satellitepull.cnr.cn/live/wxxczs/playlist.m3u8"},
    {"id": "rthk4",                 "name": "RTHK Radio 4",                        "genre": "Western + Chinese classical, Sunday Opera",                 "url": "https://rthkradio4-live.akamaized.net/hls/live/2040080/radio4/master.m3u8"},
    {"id": "rthk5",                 "name": "RTHK Radio 5",                        "genre": "Cantonese opera dedicated!",                                "url": "https://rthkradio5-live.akamaized.net/hls/live/2040081/radio5/master.m3u8"},
    {"id": "nhkr1",                 "name": "NHK Radio 1",                         "genre": "Japanese public (hōgaku, gagaku)",                          "url": "https://masterpl.hls.nhkworld.jp/hls/r1/live/master.m3u8"},
    {"id": "nhkworld",              "name": "NHK World",                           "genre": "English international",                                     "url": "https://master.nhkworld.jp/nhkworld-radio/playlist/rs2/live.m3u8"},
    {"id": "kbs1fm",                "name": "KBS 1FM Classic",                     "genre": "Korean classical — Seoul",                                  "url": "https://radio.bsod.kr/stream/?stn=kbs&ch=1fm"},
    {"id": "warna",                 "name": "Warna 94.2",                          "genre": "Malay classics & dangdut — Singapore",                      "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/WARNA942FMAAC.aac"},
    {"id": "oli968",                "name": "Oli 96.8",                            "genre": "Tamil classical — Singapore",                               "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/OLI968FMAAC.aac"},
    {"id": "capital958",            "name": "Capital 958",                         "genre": "Mandarin & Hokkien oldies — Singapore",                     "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/CAPITAL958FMAAC.aac"},
    {"id": "love972",               "name": "Love 972",                            "genre": "Mandarin classics — Singapore",                             "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/LOVE972FMAAC.aac"},
    {"id": "klasik",                "name": "Radio Klasik RTM",                    "genre": "Classic Malay, keroncong, P. Ramlee",                       "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/RADIO_KLASIK.mp3"},
    {"id": "asyik",                 "name": "Asyik FM",                            "genre": "Orang Asli indigenous",                                     "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/ASYIK_FM.mp3"},
    {"id": "waiiban",               "name": "Wai FM Iban",                         "genre": "Sarawak Iban & sape",                                       "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/WAI_FM_IBAN.mp3"},
    {"id": "waibidayuh",            "name": "Wai FM Bidayuh",                      "genre": "Sarawak Bidayuh",                                           "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/WAI_FM_BK.mp3"},
    {"id": "aifm",                  "name": "Ai FM",                               "genre": "Mandarin — Malaysia",                                       "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/AI_FMAAC.aac"},
    {"id": "cool93",                "name": "Cool Fahrenheit 93",                  "genre": "Thai & Western chill",                                      "url": "https://coolism-web.cdn.byteark.com/;stream/1"},
    {"id": "mcot1005",              "name": "MCOT FM 100.5",                       "genre": "Thai news/music — Bangkok",                                 "url": "https://lcdn.mcot.net/RadioLive/smil:fm1005_live.smil/playlist.m3u8"},
    {"id": "vov1",                  "name": "VOV1",                                "genre": "Vietnam national — Hanoi",                                  "url": "https://str.vov.gov.vn/vovlive/vov1vov5Vietnamese.sdp_aac/playlist.m3u8"},
    {"id": "voh956",                "name": "VOH FM 95.6",                         "genre": "HCMC radio",                                                "url": "https://strm.voh.com.vn/radio/channel1/chunklist_w829828563.m3u8"},
    {"id": "cityfm89",              "name": "City FM 89",                          "genre": "English & music — Pakistan",                                "url": "https://radio.cityfm89.com/stream"},
    {"id": "pblahore",              "name": "Radio Pakistan Lahore",               "genre": "Punjabi & ghazal",                                          "url": "https://whmsonic.radio.gov.pk:8026/relay"},
    {"id": "pbpeshawar",            "name": "Radio Pakistan Peshawar",             "genre": "Pashto",                                                    "url": "https://whmsonic.radio.gov.pk:8072/relay"},
    {"id": "radiolibre",            "name": "Radio Liban Libre",                   "genre": "Independent Lebanon",                                       "url": "https://edge.mixlr.com/channel/qtqeb"},
    {"id": "sawtghad",              "name": "Sawt El Ghad",                        "genre": "Popular Arabic — Beirut",                                   "url": "https://l3.itworkscdn.net/itwaudio/9030/stream"},
    {"id": "yabamazigh",            "name": "Yabiladi Amazigh",                    "genre": "Berber/Amazigh music",                                      "url": "https://radio.yabiladi.com:9002/;stream.mp3"},
    {"id": "yabchaabi",             "name": "Yabiladi Chaabi",                     "genre": "Moroccan Chaabi/folk",                                      "url": "https://radio.yabiladi.com:8102/;stream.mp3"},
    {"id": "chaine3",               "name": "Algérie Chaîne 3",                    "genre": "French RTA — Algiers",                                      "url": "https://radiochaine3.ice.infomaniak.ch/chaine3.mp3"},
    {"id": "tlemcen",               "name": "Radio Tlemcen",                       "genre": "Regional RTA — Tlemcen",                                    "url": "https://radiotlemcen.ice.infomaniak.ch/tlemcen.mp3"},
    {"id": "tiziouzou",             "name": "Radio Tizi Ouzou",                    "genre": "Kabyle/Berber — oldest Amazigh station",                    "url": "https://radiotiziouzou.ice.infomaniak.ch/tiziouzou.mp3"},
    {"id": "mostarab",              "name": "Mosaique Tarab",                      "genre": "Classical Arabic tarab",                                    "url": "https://radio.mosaiquefm.net/mosatarab"},
    {"id": "alarabiya",             "name": "Al Arabiya FM",                       "genre": "Pan-Arab news/music",                                       "url": "https://fm.alarabiya.net/fm/myStream/playlist.m3u8"},
    {"id": "ajarabic",              "name": "Al Jazeera Arabic",                   "genre": "News audio — Doha",                                         "url": "https://live-hls-audio-web-aja.getaj.net/VOICE-AJA/01.m3u8"},
    {"id": "ajenglish",             "name": "Al Jazeera English",                  "genre": "News audio — Doha",                                         "url": "https://live-hls-audio-web-aje.getaj.net/VOICE-AJE/01.m3u8"},
    {"id": "trtkurdi",              "name": "TRT Radyo Kurdî",                     "genre": "Kurdish (Kurmanji/Zaza)",                                   "url": "https://radio-trtradyo6.medya.trt.com.tr/master.m3u8"},
    {"id": "kafa",                  "name": "Kafa Radyo",                          "genre": "Turkish alternative — Istanbul",                            "url": "https://moondigitalmaster.radyotvonline.net/kafaradyo/playlist.m3u8"},
    {"id": "alaturka",              "name": "Radyo Alaturka",                      "genre": "Turkish classical sanat",                                   "url": "https://yayin.jumboserver.net:9100/stream"},
    {"id": "dinamocaffe",           "name": "Dinamo Caffe",                        "genre": "Anatolian/jazz — Istanbul",                                 "url": "https://channels.dinamo.fm/caffe-mp3"},
    {"id": "dinamolegacy",          "name": "Dinamo Legacy",                       "genre": "Classic Anatolian rock",                                    "url": "https://channels.dinamo.fm/legacy-mp3"},
    {"id": "dinamosmog",            "name": "Dinamo Smog",                         "genre": "Dub/electronic",                                            "url": "https://channels.dinamo.fm/smog-mp3"},
    {"id": "kurdistan24",           "name": "Kurdistan 24 Radio",                  "genre": "Kurdish news — Erbil",                                      "url": "https://audio-edge-3mayu.fra.h.radiomast.io/04b1ce4c-24f2-4172-b756-065832ef78bf"},
    {"id": "rudaw",                 "name": "Rudaw News Radio",                    "genre": "Kurdish news — Erbil",                                      "url": "https://l3.itworkscdn.net/itwaudio/9006/stream"},
    {"id": "kan88",                 "name": "Kan 88",                              "genre": "Israeli jazz & world",                                      "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/KAN_88.mp3"},
    {"id": "kanklass",              "name": "Kan Kol HaMusica",                    "genre": "Israeli classical",                                         "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/KAN_KOL_HAMUSICA.mp3"},
    {"id": "kangimmel",             "name": "Kan Gimmel",                          "genre": "Israeli music, Mizrahi rotation",                           "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/KAN_GIMMEL.mp3"},
    {"id": "kanreka",               "name": "Kan Reka",                            "genre": "Multilingual immigrant radio",                              "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/KAN_REKA.mp3"},
    {"id": "kanmoreshet",           "name": "Kan Moreshet",                        "genre": "Heritage/religious",                                        "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/KAN_MORESHET.mp3"},
    {"id": "kantarbut",             "name": "Kan Tarbut",                          "genre": "Israeli culture/talk",                                      "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/KAN_TARBUT.mp3"},
    {"id": "mizrahit",              "name": "Mizrahit Radio",                      "genre": "Mizrahi dedicated",                                         "url": "https://mzr.mediacast.co.il/mzradio"},
    {"id": "ashams",                "name": "Radio A-Shams",                       "genre": "Arabic for Arab Israelis",                                  "url": "https://cdna.streamgates.net/Ashams/Live/icecast.audio"},
    {"id": "opus94",                "name": "IMER Opus 94",                        "genre": "Mexican classical",                                         "url": "https://s2.mexside.net/8016/stream"},
    {"id": "horizonte",             "name": "IMER Horizonte",                      "genre": "Mexican jazz & world",                                      "url": "https://s2.mexside.net/8014/stream"},
    {"id": "reactor",               "name": "IMER Reactor",                        "genre": "Mexican indie & alternative",                               "url": "https://s2.mexside.net/8002/stream"},
    {"id": "radiounam",             "name": "Radio UNAM 96.1",                     "genre": "Cultural university — CDMX",                                "url": "https://tv.radiohosting.online:9484/stream"},
    {"id": "tgw",                   "name": "TGW La Voz de Guatemala",             "genre": "National public, marimba",                                  "url": "https://stream.radiotgw.gob.gt/8002/stream"},
    {"id": "radionalcol",           "name": "Radio Nacional Colombia",             "genre": "Cultural, regional, indigenous",                            "url": "https://streaming.rtvc.gov.co/Radio_Radionacional/Radionacional.stream/playlist.m3u8"},
    {"id": "radionica",             "name": "Señal Radiónica",                     "genre": "Colombian indie/alternative",                               "url": "https://streaming.rtvc.gov.co/Radio_Radionica/Radionica.stream/playlist.m3u8"},
    {"id": "filarmonia",            "name": "Radio Filarmonía",                    "genre": "Peruvian classical — Lima",                                 "url": "https://c22.radioboss.fm:18100/live"},
    {"id": "radiouchile",           "name": "Radio Universidad de Chile",          "genre": "Nueva Canción heritage",                                    "url": "https://sonic-us.arkeo.cl/8186/stream"},
    {"id": "radiocultura",          "name": "Radio Cultura Buenos Aires",          "genre": "Argentine classical/cultural",                              "url": "https://streaming.escuchanosonline.com:7035/stream"},
    {"id": "radiouruguay",          "name": "Radio Uruguay SODRE",                 "genre": "National public — Montevideo",                              "url": "https://radios.iwstreaming.uy/8036/stream"},
    {"id": "emisorasur",            "name": "SODRE Emisora del Sur",               "genre": "Candombe, murga, tango",                                    "url": "https://radios.iwstreaming.uy/8034/stream"},
    {"id": "babelfm",               "name": "Babel FM SODRE",                      "genre": "World music — Uruguay",                                     "url": "https://radios.iwstreaming.uy/8030/stream"},
    {"id": "batuta",                "name": "Rádio Batuta MPB",                    "genre": "IMS MPB, samba, choro",                                     "url": "https://radioims.out.airtime.pro:8443/radioims_a"},
    {"id": "batutaclass",           "name": "Rádio Batuta Clássicos",              "genre": "IMS classical archive",                                     "url": "https://classicoims.out.airtime.pro:8443/classicoims_a"},
    {"id": "mecfm",                 "name": "Rádio MEC FM",                        "genre": "Brazilian classical/cultural",                              "url": "https://radiomecfm-stream.ebc.com.br/ebc/radiomecfm/playlist.m3u8"},
    {"id": "amazonia",              "name": "Rádio Nacional Amazônia",             "genre": "Northern Brazil, indigenous",                               "url": "https://radionacionalamazonia-stream.ebc.com.br/ebc/radionacionalamazonia/playlist.m3u8"},
    {"id": "culturasp",             "name": "Cultura FM São Paulo",                "genre": "Brazilian classical/cultural",                              "url": "https://player-culturafm.stream.uol.com.br/live/culturafm.m3u8"},
    {"id": "alphafm",               "name": "Alpha FM",                            "genre": "Brazilian instrumental/smooth",                             "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/RADIO_ALPHAFM_ADP.aac"},
    {"id": "uspfm",                 "name": "Rádio USP FM",                        "genre": "University cultural — SP",                                  "url": "https://flow.emm.usp.br:8008/radiousp-rp-64.mp3"},
    {"id": "vibect",                "name": "Vibe CT 105",                         "genre": "Trinidad soca/calypso",                                     "url": "https://audio-edge-vqwx4.yyz.g.radiomast.io/c35d311e-cc60-41b9-b0c5-339e62c14dee"},
    {"id": "kooriradio",            "name": "Koori Radio",                         "genre": "Sydney First Nations",                                      "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/2LND.mp3"},
    {"id": "triplernation",         "name": "ABC Radio National",                  "genre": "Australian culture/talk",                                   "url": "https://mediaserviceslive.akamaized.net/hls/live/2038316/radionational/index.m3u8"},
    {"id": "triplej",               "name": "ABC Triple J",                        "genre": "Youth/alt music",                                           "url": "https://mediaserviceslive.akamaized.net/hls/live/2038316/triplej/index.m3u8"},
    {"id": "doublej",               "name": "ABC Double J",                        "genre": "Grown-up alt rock",                                         "url": "https://mediaserviceslive.akamaized.net/hls/live/2038316/doublej/index.m3u8"},
    {"id": "abccountry",            "name": "ABC Country",                         "genre": "Australian country & folk",                                 "url": "https://mediaserviceslive.akamaized.net/hls/live/2038316/country/index.m3u8"},
    {"id": "triplerr",              "name": "Triple R 102.7",                      "genre": "Melbourne community eclectic",                              "url": "https://ondemand.rrr.org.au/getstream?id=wshq"},
    {"id": "niufm",                 "name": "Niu FM 103.8",                        "genre": "Pasifika — Auckland",                                       "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/NIUFMAAC.aac"},
    {"id": "waatea",                "name": "Radio Waatea",                        "genre": "Urban Māori — Auckland",                                    "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/NZME_223AAC.aac"},
    {"id": "tehiku",                "name": "Te Hiku Media",                       "genre": "Iwi te reo Māori — Kaitaia",                                "url": "https://wowza.iwi.radio/icecast-to-hls/ngrp:TeHikuMedia.stream_all/playlist.m3u8"},
    {"id": "nv1",                   "name": "Native Voice One",                    "genre": "US Native American network",                                "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/NV1.mp3"},
    {"id": "hpr1",                  "name": "HPR-1 Hawaii",                        "genre": "Hawaiian public, slack-key Sundays",                        "url": "https://khpr-ice.streamguys1.com/khpr2.mp3"},
    {"id": "hpr2",                  "name": "HPR-2 Hawaii",                        "genre": "Hawaiian public classical",                                 "url": "https://khpr-ice.streamguys1.com/kipo2.mp3"},
    {"id": "ckua",                  "name": "CKUA Radio",                          "genre": "Alberta's eclectic public radio",                           "url": "https://ais-sa1.streamon.fm/7000_48k.aac/playlist.m3u8"},
    {"id": "cbconetor",             "name": "CBC Radio One Toronto",               "genre": "Canadian news/talk",                                        "url": "https://cbcradiolive.akamaized.net/hls/live/2041036/ES_R1ETR/master.m3u8"},
    {"id": "wmbr",                  "name": "WMBR",                                "genre": "MIT community eclectic",                                    "url": "https://wmbr.org:8002/hi"},
    {"id": "kalx",                  "name": "KALX Berkeley",                       "genre": "UC Berkeley college radio",                                 "url": "https://stream.kalx.berkeley.edu:8443/kalx-128.mp3"},
    {"id": "kcsb",                  "name": "KCSB Santa Barbara",                  "genre": "UCSB college radio",                                        "url": "https://stream.revma.ihrhls.com/zc185"},
    {"id": "finter",                "name": "France Inter",                        "genre": "Public culture/news/music",                                 "url": "https://icecast.radiofrance.fr/franceinter-midfi.mp3"},
    {"id": "fmusique",              "name": "France Musique",                      "genre": "Classical, jazz, contemporary",                             "url": "https://icecast.radiofrance.fr/francemusique-midfi.mp3"},
    {"id": "novaparis",             "name": "Radio Nova Paris",                    "genre": "Afro, Balkan, global crate-digging",                        "url": "https://novazz.ice.infomaniak.ch/novazz-128.mp3"},
    {"id": "cosmo",                 "name": "WDR Cosmo",                           "genre": "9-language world/diaspora — Cologne",                       "url": "https://wdr-cosmo-live.icecast.wdr.de/wdr/cosmo/live/mp3/128/stream.mp3"},
    {"id": "dlfkultur",             "name": "Deutschlandfunk Kultur",              "genre": "German public culture",                                     "url": "https://st02.sslstream.dlf.de/dlf/02/128/mp3/stream.mp3?aggregator=web"},
    {"id": "orfoe1",                "name": "ORF Ö1",                              "genre": "Austrian public culture/music",                             "url": "https://orf-live.ors-shoutcast.at/oe1-q2a"},
    {"id": "yleklass",              "name": "YLE Klassinen",                       "genre": "Finnish public classical",                                  "url": "https://icecast.live.yle.fi/radio/YleKlassinen/icecast.audio"},
    {"id": "drp2",                  "name": "DR P2",                               "genre": "Danish public classical",                                   "url": "https://live-icy.gss.dr.dk/A/A05H.mp3"},
    {"id": "drp8jazz",              "name": "DR P8 Jazz",                          "genre": "Danish public jazz",                                        "url": "https://live-icy.gss.dr.dk/A/A22H.mp3"},
    {"id": "klara",                 "name": "Klara VRT",                           "genre": "Flemish classical/world",                                   "url": "https://quantumcast.vrtcdn.be/klara/mp3-128"},
    {"id": "rai5",                  "name": "RAI Radio 5 Classica",                "genre": "Italian public classical",                                  "url": "https://icestreaming.rai.it/5.mp3"},
    {"id": "espace2",               "name": "RTS Espace 2",                        "genre": "Swiss French classical/culture",                            "url": "https://stream.srg-ssr.ch/m/espace-2/mp3_128"},
    {"id": "retedue",               "name": "RSI Rete Due",                        "genre": "Swiss Italian culture",                                     "url": "https://stream.srg-ssr.ch/m/rsp/mp3_128"},
    {"id": "bnrhoro",               "name": "BNR Radio Horo",                      "genre": "Bulgarian folk 24/7 — Sofia",                               "url": "https://lb-hls.cdn.bg/2032/fls/RadioHoro.stream/playlist.m3u8"},
    {"id": "errklass",              "name": "ERR Klassikaraadio",                  "genre": "Estonian public classical",                                 "url": "https://icecast.err.ee/klassikaraadio.mp3"},
    {"id": "errklarajazz",          "name": "ERR Klara Jazz",                      "genre": "Estonian public jazz",                                      "url": "https://icecast.err.ee/klarajazz.mp3"},
    {"id": "tilos",                 "name": "Tilos Rádió",                         "genre": "Budapest independent community",                            "url": "https://stream.tilos.hu/tilos"},
    {"id": "kioskradio",            "name": "Kiosk Radio",                         "genre": "Curated, Nyege Nyege partner — Brussels",                   "url": "https://kioskradiobxl.out.airtime.pro/kioskradiobxl_a"},
    {"id": "raheem",                "name": "Radio Raheem",                        "genre": "Independent culture — Milan",                               "url": "https://radioraheem.out.airtime.pro/radioraheem_a"},
    {"id": "czlive",                "name": "Concertzender Live",                  "genre": "Classical/jazz/world main stream",                          "url": "https://streams.greenhost.nl:8006/live"},
    {"id": "czworld",               "name": "Concertzender Wereldmuziek",          "genre": "World music — Utrecht",                                     "url": "https://streams.greenhost.nl:8006/wereldmuziek"},
    {"id": "czfolk",                "name": "Concertzender Folk it!",              "genre": "Folk — Utrecht",                                            "url": "https://streams.greenhost.nl:8006/folkit"},
    {"id": "czorient",              "name": "Concertzender Oriënt Express",        "genre": "Middle Eastern/Asian",                                      "url": "https://streams.greenhost.nl:8006/orientexpress"},
    {"id": "czchanson",             "name": "Concertzender Chanson",               "genre": "French chanson",                                            "url": "https://streams.greenhost.nl:8006/chanson"},
    {"id": "czgregorian",           "name": "Concertzender Gregoriaans",           "genre": "Gregorian chant",                                           "url": "https://streams.greenhost.nl:8006/gregoriaans"},
    {"id": "czearly",               "name": "Concertzender Oude Muziek",           "genre": "Early music",                                               "url": "https://streams.greenhost.nl:8006/oudemuziek"},
    {"id": "czopera",               "name": "Concertzender Opera",                 "genre": "Opera",                                                     "url": "https://streams.greenhost.nl:8006/opera"},
    {"id": "czbarok",               "name": "Concertzender Barok",                 "genre": "Baroque",                                                   "url": "https://streams.greenhost.nl:8006/barok"},
    {"id": "czjazz",                "name": "Concertzender Jazz",                  "genre": "World of Jazz",                                             "url": "https://streams.greenhost.nl:8006/jazz"},    # --- Added in parallel research round ---
    {"id": "citifm",                "name": "Citi FM 97.3",                        "genre": "English news/talk — Accra, Ghana",                          "url": "https://citi973fm.radioca.st/;stream.mp3"},
    {"id": "brilafm",               "name": "Brila FM",                            "genre": "Sports talk — Lagos",                                       "url": "https://atunwadigital.streamguys1.com/brilafm"},
    {"id": "zikfm",                 "name": "Zik FM 89.7",                         "genre": "Pop/R&B/rap — Dakar, Senegal",                              "url": "https://stream.zenolive.com/2a5a6ry9sxquv"},
    {"id": "rfmsn",                 "name": "RFM 94.0",                            "genre": "Wolof/French — Dakar",                                      "url": "https://stream.zeno.fm/kuk0syz5puquv"},
    {"id": "crtv",                  "name": "CRTV Radio",                          "genre": "Cameroonian national — Yaoundé",                            "url": "https://listen.radioking.com/radio/39218/stream/75659"},
    {"id": "tbctaifa",              "name": "TBC Taifa",                           "genre": "Swahili public radio — Dar es Salaam",                      "url": "https://a7.asurahosting.com:7890/listen.mp3"},
    {"id": "rsg",                   "name": "RSG (Radio Sonder Grense)",           "genre": "Afrikaans — South Africa",                                  "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/RSGAAC_SC"},
    {"id": "safm",                  "name": "SAfm",                                "genre": "English news/talk — South Africa",                          "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/SAFMAAC_SC"},
    {"id": "lmmoz",                 "name": "LM Radio Mozambique",                 "genre": "English oldies — Maputo",                                   "url": "https://edge.iono.fm/xice/392_medium.mp3"},
    {"id": "aircuttack",            "name": "AIR Cuttack",                         "genre": "Odia folk/classical",                                       "url": "https://air.pc.cdn.bitgravity.com/air/live/pbaudio137/playlist.m3u8"},
    {"id": "rthk1",                 "name": "RTHK Radio 1",                        "genre": "Cantonese talk/news — Hong Kong",                           "url": "https://rthkradio1-live.akamaized.net/hls/live/2035313/radio1/master.m3u8"},
    {"id": "rthk2",                 "name": "RTHK Radio 2",                        "genre": "Cantopop & youth — Hong Kong",                              "url": "https://rthkradio2-live.akamaized.net/hls/live/2040078/radio2/index_64_a.m3u8"},
    {"id": "rthk3",                 "name": "RTHK Radio 3",                        "genre": "English service — Hong Kong",                               "url": "https://rthkradio3-live.akamaized.net/hls/live/2040079/radio3/master.m3u8"},
    {"id": "cnr1",                  "name": "CNR-1 National",                      "genre": "China national news/culture",                               "url": "https://satellitepull.cnr.cn/live/wxzgzs/playlist.m3u8"},
    {"id": "jia883",                "name": "Jia 88.3",                            "genre": "Hokkien/Cantonese/Teochew — Singapore",                     "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/883JIAAAC.aac"},
    {"id": "nasional",              "name": "Nasional FM",                         "genre": "Malay news/talk — Kuala Lumpur",                            "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/NASIONAL_FM.mp3"},
    {"id": "minnal",                "name": "Minnal FM",                           "genre": "Tamil — Malaysia",                                          "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/MINNAL_FMAAC.aac"},
    {"id": "mcotchiangmai",         "name": "MCOT Chiang Mai",                     "genre": "Northern Thai — Chiang Mai",                                "url": "https://live-org-01-cdn.mcot.net/RegionRadio/ChiangMai.stream_aac/playlist.m3u8"},
    {"id": "bkkfm",                 "name": "BKK.FM",                              "genre": "Bangkok indie/Thai",                                        "url": "https://rsas.bkk.fm/radio"},
    {"id": "voh610",                "name": "VOH AM 610",                          "genre": "HCMC traditional",                                          "url": "https://strm.voh.com.vn/radio/channel2/chunklist_w884773542.m3u8"},
    {"id": "voh999",                "name": "VOH FM 99.9",                         "genre": "HCMC",                                                      "url": "https://strm.voh.com.vn/radio/channel3/chunklist_w1005696319.m3u8"},
    {"id": "voh877",                "name": "VOH FM 87.7",                         "genre": "HCMC traffic/news",                                         "url": "https://strm.voh.com.vn/radio/channel5/chunklist_w2071193605.m3u8"},
    {"id": "vovgthn",               "name": "VOV Giao thông Hà Nội",               "genre": "Hanoi traffic",                                             "url": "https://play.vovgiaothong.vn/live/gthn/playlist.m3u8"},
    {"id": "vovgthcm",              "name": "VOV Giao thông HCM",                  "genre": "HCMC traffic",                                              "url": "https://play.vovgiaothong.vn/live/gthcm/playlist.m3u8"},
    {"id": "pbislamabad",           "name": "Radio Pakistan Islamabad",            "genre": "PBC national",                                              "url": "https://whmsonic.radio.gov.pk:7003/stream"},
    {"id": "asiafm",                "name": "AsiaFM",                              "genre": "Mandarin pop — Taiwan",                                     "url": "https://n13.rcs.revma.com/kydend74hv8uv"},
    {"id": "rrijakarta1",           "name": "RRI Pro 1 Jakarta",                   "genre": "National Indonesian",                                       "url": "https://stream-node1.rri.co.id/streaming/25/9025/rrijakartapro1.mp3"},
    {"id": "rriambon",              "name": "RRI Pro 4 Ambon Budaya",              "genre": "Ambon regional culture",                                    "url": "https://stream-node2.rri.co.id/streaming/15/9315/rriambonpro4.mp3"},
    {"id": "rribandung",            "name": "RRI Pro 4 Bandung Budaya",            "genre": "Sundanese culture",                                         "url": "https://stream-node0.rri.co.id/streaming/15/9015/rribandungpro4.mp3"},
    {"id": "rrikbrn",               "name": "RRI Pro 3 KBRN",                      "genre": "Indonesia national news",                                   "url": "https://stream-node0.rri.co.id/streaming/14/9014/kbrn.mp3"},
    {"id": "sawtleb",               "name": "Sawt Lebanon",                        "genre": "Voice of Lebanon — talk/news",                              "url": "https://l3.itworkscdn.net/itwaudio/9054/stream"},
    {"id": "radiomars",             "name": "Radio Mars",                          "genre": "Sports & culture — Casablanca",                             "url": "https://radiomars.ice.infomaniak.ch/radiomars-128.mp3"},
    {"id": "zitouna",               "name": "Radio Zitouna FM",                    "genre": "Quranic/Islamic — Tunis",                                   "url": "https://radio.radiotunisienne.tn/radiozaitouna"},
    {"id": "alifalif",              "name": "Alif Alif FM",                        "genre": "Arabic music — Riyadh",                                     "url": "https://alifalifjobs.com/radio/8000/AlifAlifLive.mp3"},
    {"id": "alaraby",               "name": "Al Araby Radio",                      "genre": "Pan-Arab news — Doha/London",                               "url": "https://l3.itworkscdn.net/alarabyradiolive/alarabyradio_audio/icecast.audio"},
    {"id": "trthaber",              "name": "TRT Radyo Haber",                     "genre": "Turkish news",                                              "url": "https://rd-trtradyohaber.medya.trt.com.tr/master.m3u8"},
    {"id": "dinamodeep",            "name": "Dinamo Deep",                         "genre": "Deep house/electronic — Istanbul",                          "url": "https://channels.dinamo.fm/deep-mp3"},
    {"id": "dinamofluent",          "name": "Dinamo Fluent",                       "genre": "Downtempo lounge — Istanbul",                               "url": "https://channels.dinamo.fm/fluent-mp3"},
    {"id": "dinamolocodyno",        "name": "Dinamo Locodyno",                     "genre": "Latin/world — Istanbul",                                    "url": "https://channels.dinamo.fm/locodyno-mp3"},
    {"id": "dinamommradyo",         "name": "Dinamo MinimuzikHol",                 "genre": "Live club radio — Istanbul",                                "url": "https://channels.dinamo.fm/mmradyo-mp3"},
    {"id": "iraniintl",             "name": "Iran International Radio",            "genre": "Persian diaspora news — London",                            "url": "https://stream.radiojar.com/iintl_c"},
    {"id": "kanbet",                "name": "Kan Bet (Reshet Bet)",                "genre": "Israeli news/talk",                                         "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/KAN_BET.mp3"},
    {"id": "tlv103",                "name": "103FM",                               "genre": "News/talk — Tel Aviv",                                      "url": "https://cdn.cybercdn.live/103FM/Live/icecast.audio"},
    {"id": "radiounam860",          "name": "Radio UNAM 860 AM",                   "genre": "Cultural university — CDMX",                                "url": "https://tv.radiohosting.online:9486/stream"},
    {"id": "radiogaucha",           "name": "Rádio Gaúcha",                        "genre": "News/talk — Porto Alegre",                                  "url": "https://1132747t.ha.azioncdn.net/primary/gaucha_rbs.sdp/playlist.m3u8"},
    {"id": "abckids",               "name": "ABC Kids Listen",                     "genre": "Kids stories & songs — Australia",                          "url": "https://mediaserviceslive.akamaized.net/hls/live/2038316/kids/index.m3u8"},
    {"id": "cbconevan",             "name": "CBC Radio One Vancouver",             "genre": "Canadian news/talk",                                        "url": "https://cbcradiolive.akamaized.net/hls/live/2041050/ES_R1PVC/master.m3u8"},
    {"id": "errklara",              "name": "ERR Klara Klassika",                  "genre": "Estonian classical thematic",                               "url": "https://icecast.err.ee/klaraklassika.mp3"},


    {"id": "rbcradio",      "name": "РБК Радио",               "genre": "Business news & talk — Moscow, Russia",        "url": "https://hls-01-rbc.hostingradio.ru/rbc-fed0/112/playlist.m3u8"},
    # --- Custom ---
    {"id": "custom",        "name": "Custom URL",             "genre": "Paste any stream URL",                          "url": ""},
]

FALLBACK_STREAMS = {
    "wkcr": ["http://wkcr.streamguys1.com/live"],
    "fip": ["http://direct.fipradio.fr/live/fip-midfi.mp3"],
}

# --- Shared playback state ---
_play_lock = threading.Lock()
_playing_station_id = None
_playing_station_name = None
_playing_device = None
_stop_grace_until = 0

# --- Chromecast cache ---
_cast_cache = {}
_cast_lock = threading.Lock()
_discovered = []

# Per-device state used to avoid redundant Chromecast round-trips.
# _cast_last_ok[name] = monotonic timestamp of last confirmed-healthy contact
# _cast_last_vol[name] = integer volume (0-100) last successfully set
# _cast_last_url[name] = last stream URL we told this device to play
_cast_last_ok = {}
_cast_last_vol = {}
_cast_last_url = {}

# --- Alarm state ---
_alarm_last_triggered_minute = None


def _load_config():
    """Load config from file with atomic read and defaults."""
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
    except Exception as e:
        LOG.error(f"Error loading config: {e}")

    return {
        "device_name": "Living Room",
        "station": "wkcr",
        "volume": 50,
        "alarm_enabled": False,
        "alarm_time": "07:00",
        "alarm_days": [1, 2, 3, 4, 5],  # Monday-Friday
        "alarm_station": "wkcr",
        "custom_url": "",
    }


def _save_config(cfg):
    """Save config to file with atomic write."""
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH) or ".", exist_ok=True)
        # Write to temp file first, then rename for atomicity
        temp_path = CONFIG_PATH + ".tmp"
        with open(temp_path, "w") as f:
            json.dump(cfg, f, indent=2)
        os.replace(temp_path, CONFIG_PATH)
        LOG.info("Config saved successfully")
    except Exception as e:
        LOG.error(f"Error saving config: {e}")


def _get_cast(name):
    """
    Three-phase cache pattern:
    1. Check cache (locked)
    2. Discover if not found (UNLOCKED)
    3. Store result (locked)
    """
    with _cast_lock:
        if name in _cast_cache:
            return _cast_cache[name]

    # Discover devices without lock
    try:
        chromecasts, browser = pychromecast.get_listed_chromecasts(
            friendly_names=[name], discovery_timeout=8
        )
        browser.stop_discovery()
        if chromecasts:
            cast = chromecasts[0]
            cast.wait()
            with _cast_lock:
                _cast_cache[cast.name] = cast
            return cast
    except Exception as e:
        LOG.error(f"Error discovering Chromecast '{name}': {e}")

    return None


def _find_station(station_id):
    """Find station in STATIONS by ID."""
    for station in STATIONS:
        if station["id"] == station_id:
            return station
    return None


def _guess_mime(url):
    """Guess MIME type from stream URL so Chromecast picks the right decoder fast."""
    u = url.lower()
    if u.endswith(".aac") or "/aac" in u or "-hifi.aac" in u:
        return "audio/aac"
    if u.endswith(".ogg") or "/ogg" in u:
        return "audio/ogg"
    if u.endswith(".flac") or "/flac" in u:
        return "audio/flac"
    if u.endswith(".m3u8"):
        return "application/x-mpegURL"
    # Default to mpeg for .mp3 and everything else
    return "audio/mpeg"


def play_station(station_id, device_name, vol, custom_url=""):
    """
    Play a station on a Chromecast device.
    Updates shared playback state.
    """
    global _playing_station_id, _playing_station_name, _playing_device, _stop_grace_until

    station = _find_station(station_id)
    if not station:
        LOG.error(f"Station '{station_id}' not found")
        return False

    stream_url = custom_url if custom_url and station_id == "custom" else station["url"]
    if not stream_url:
        LOG.error(f"No stream URL for station '{station_id}'")
        return False

    cast = _get_cast(device_name)
    if not cast:
        LOG.error(f"Chromecast device '{device_name}' not found")
        return False

    try:
        # Skip cast.wait() if we had confirmed-healthy contact with this cast
        # within the last 60s — the connection is known alive, so the blocking
        # handshake is pure overhead and adds 100-3000ms per switch.
        last_ok = _cast_last_ok.get(device_name, 0)
        needs_wait = (time.monotonic() - last_ok) > 60
        if needs_wait:
            try:
                cast.wait(timeout=3)
            except Exception:
                LOG.info(f"Stale connection to '{device_name}', re-discovering")
                with _cast_lock:
                    _cast_cache.pop(device_name, None)
                _cast_last_ok.pop(device_name, None)
                _cast_last_vol.pop(device_name, None)
                _cast_last_url.pop(device_name, None)
                cast = _get_cast(device_name)
                if not cast:
                    return False
                cast.wait(timeout=5)
        mc = cast.media_controller

        # Normalize volume: ensure integer 0-100, convert to 0.0-1.0 for Chromecast
        if isinstance(vol, float) and vol <= 1.0:
            vol = int(vol * 100)  # Was stored as fraction, convert to percent
        vol = max(0, min(100, int(vol)))

        # Skip redundant set_volume — saves ~500-1000ms per switch when the
        # user is just flipping stations without touching the slider.
        if _cast_last_vol.get(device_name) != vol:
            cast.set_volume(vol / 100.0)
            _cast_last_vol[device_name] = vol

        # Detect correct MIME type and tell Chromecast this is a LIVE stream
        mime = _guess_mime(stream_url)
        mc.play_media(stream_url, mime, stream_type="LIVE")
        _cast_last_url[device_name] = stream_url
        _cast_last_ok[device_name] = time.monotonic()

        # Update shared state
        with _play_lock:
            _playing_station_id = station_id
            _playing_station_name = station["name"]
            _playing_device = device_name
            _stop_grace_until = 0

        LOG.info(f"Now playing: {station['name']} on {device_name} at volume {vol}% (mime={mime}, skipVol={_cast_last_vol.get(device_name)==vol and not needs_wait})")
        return True
    except Exception as e:
        LOG.error(f"Error playing station: {e}")
        # Connection may have failed mid-call; invalidate so next call re-checks
        _cast_last_ok.pop(device_name, None)
        return False


def stop_playback(device_name):
    """
    Stop playback with grace period.
    Uses quit_app() + mc.stop() + grace period to prevent resurrection.
    """
    global _playing_station_id, _playing_station_name, _playing_device, _stop_grace_until

    cast = _get_cast(device_name)
    if not cast:
        LOG.warning(f"Chromecast device '{device_name}' not found for stop")
        with _play_lock:
            _playing_station_id = None
            _playing_station_name = None
            _playing_device = None
        return True

    try:
        cast.wait()
        mc = cast.media_controller

        # Triple-layer stop: quit_app, stop, grace period
        try:
            cast.quit_app()
            LOG.info(f"Quit app on {device_name}")
        except Exception as e:
            LOG.warning(f"Error quitting app: {e}")

        try:
            mc.stop()
            LOG.info(f"Stopped media on {device_name}")
        except Exception as e:
            LOG.warning(f"Error stopping media: {e}")

        # Update shared state with grace period
        with _play_lock:
            _playing_station_id = None
            _playing_station_name = None
            _playing_device = None
            _stop_grace_until = time.time() + STOP_GRACE_SECONDS

        return True
    except Exception as e:
        LOG.error(f"Error stopping playback: {e}")
        with _play_lock:
            _playing_station_id = None
            _playing_station_name = None
            _playing_device = None
        return False


def check_alarm():
    """
    Check if alarm should trigger.
    Runs every 30 seconds. Uses a unique per-day key (YYYY-MM-DD HH:MM) so
    the debounce doesn't persist across days.
    """
    global _alarm_last_triggered_minute

    cfg = _load_config()

    if not cfg.get("alarm_enabled"):
        return

    now = datetime.now()
    current_day = now.weekday()  # 0=Monday, 6=Sunday

    alarm_time_str = cfg.get("alarm_time", "07:00")
    try:
        alarm_hour, alarm_minute = map(int, alarm_time_str.split(":"))
    except:
        LOG.warning(f"Invalid alarm_time format: {alarm_time_str}")
        return

    alarm_days = cfg.get("alarm_days", [])

    # Unique key per calendar minute (e.g. "2026-04-17 06:30") — prevents
    # double-fire within a minute but still fires the same time the next day.
    trigger_key = now.strftime("%Y-%m-%d %H:%M")

    if (now.hour == alarm_hour and now.minute == alarm_minute and
            current_day in alarm_days and
            _alarm_last_triggered_minute != trigger_key):

        _alarm_last_triggered_minute = trigger_key

        device_name = cfg.get("device_name", "Living Room")
        alarm_station = cfg.get("alarm_station", cfg.get("station", "wkcr"))
        volume = cfg.get("volume", 50)

        LOG.info(f"Triggering alarm: {alarm_station} on {device_name} (key={trigger_key})")
        play_station(alarm_station, device_name, volume)


def alarm_thread_worker():
    """Background thread that checks alarm every 30 seconds."""
    while True:
        try:
            check_alarm()
        except Exception as e:
            LOG.error(f"Error in alarm thread: {e}")
        time.sleep(30)


def cast_keepalive_worker():
    """
    Periodically exercise each cached Chromecast connection so its socket
    doesn't go stale. This prevents the 'first tap takes 30 seconds because
    pychromecast has to reconnect' problem that users experience when the
    connection has been idle.

    Runs every 90 seconds. If a cast is unreachable, we drop it from the cache
    so the next _get_cast() call triggers a fresh discovery rather than
    blocking on cast.wait() for a dead socket.
    """
    while True:
        time.sleep(90)
        try:
            with _cast_lock:
                names = list(_cast_cache.keys())
            for name in names:
                try:
                    with _cast_lock:
                        cast = _cast_cache.get(name)
                    if cast is None:
                        continue
                    # Touch the connection. Any of these will fail fast if the
                    # socket is dead. We pick .status which is a lightweight
                    # property access that goes over the existing connection.
                    _ = cast.status
                    # Mark this cast as known-healthy so the next user action
                    # can skip the cast.wait() handshake.
                    _cast_last_ok[name] = time.monotonic()
                except Exception as e:
                    LOG.warning(f"Keep-alive: dropping stale cast '{name}': {e}")
                    with _cast_lock:
                        _cast_cache.pop(name, None)
                    _cast_last_ok.pop(name, None)
                    _cast_last_vol.pop(name, None)
                    _cast_last_url.pop(name, None)
        except Exception as e:
            LOG.error(f"Error in keep-alive thread: {e}")


# --- Routes ---

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"ok": True, "status": "running", "devices": len(_discovered)})


@app.route("/volume-status", methods=["GET"])
def volume_status():
    """Read current volume from a Chromecast device."""
    device_name = request.args.get("device_name", "")
    if not device_name:
        return jsonify({"ok": False, "message": "Missing device_name"}), 400

    cast = _get_cast(device_name)
    if not cast:
        return jsonify({"ok": False, "message": f"Device '{device_name}' not found"}), 404

    try:
        cast.wait()
        vol = cast.status.volume_level  # 0.0 - 1.0
        return jsonify({"ok": True, "volume": vol, "device": device_name})
    except Exception as e:
        LOG.error(f"Error reading volume from {device_name}: {e}")
        return jsonify({"ok": False, "message": str(e)}), 500


@app.route("/")
def index():
    """Serve the UI."""
    ui_path = os.path.join(os.path.dirname(__file__), "ui.html")
    if os.path.exists(ui_path):
        return send_file(ui_path)
    return "<h1>Radio Alarm Clock</h1><p>UI file not found</p>", 404


# =============================================================================
# Wall-mounted dashboard (weather, MTA trains, clock)
# =============================================================================

# Greenpoint (near Nassau Ave) — 11222
DASHBOARD_LAT = 40.724
DASHBOARD_LON = -73.951

# MTA stop IDs for the L line stations we care about.
# Northbound (N) / Southbound (S) suffixes identify platform direction.
# L17N/L17S = Bedford Av, L16N/L16S = Lorimer St (nearest to Graham via L/G
# transfer), L15N/L15S = Graham Av, L14N/L14S = Grand St, L13N/L13S = Nassau Av.
MTA_L_STATIONS = {
    "Nassau Av": {"N": "L13N", "S": "L13S"},  # towards Manhattan / Canarsie
    "Graham Av": {"N": "L15N", "S": "L15S"},
    "Bedford Av": {"N": "L17N", "S": "L17S"},
}
MTA_L_FEED_URL = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-l"

# Simple TTL caches to avoid hammering upstream APIs
_dash_cache = {
    "weather": {"data": None, "ts": 0, "ttl": 600},   # 10 min
    "trains":  {"data": None, "ts": 0, "ttl": 15},    # 15 sec (MTA updates ~30s)
}
_dash_lock = threading.Lock()


def _cache_get(key):
    entry = _dash_cache.get(key)
    if not entry or not entry["data"]:
        return None
    if time.time() - entry["ts"] > entry["ttl"]:
        return None
    return entry["data"]


def _cache_put(key, data):
    _dash_cache[key]["data"] = data
    _dash_cache[key]["ts"] = time.time()


def _fetch_weather():
    """Hit Open-Meteo for current conditions + hourly forecast. No API key."""
    params = {
        "latitude": DASHBOARD_LAT,
        "longitude": DASHBOARD_LON,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,is_day",
        "hourly": "temperature_2m,weather_code,precipitation_probability",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "timezone": "America/New_York",
        "forecast_days": 2,
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "SensoryRadio-Dashboard/1.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def _fetch_mta_trains():
    """Fetch L-line GTFS-RT feed and extract upcoming arrivals per station."""
    # Import lazily so the radio app still loads if the lib isn't installed.
    try:
        from google.transit import gtfs_realtime_pb2  # pip install gtfs-realtime-bindings
    except ImportError:
        LOG.warning("gtfs-realtime-bindings not installed — /api/trains will return empty")
        return {"stations": [], "error": "missing gtfs-realtime-bindings"}

    req = urllib.request.Request(MTA_L_FEED_URL, headers={"User-Agent": "SensoryRadio-Dashboard/1.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        raw = r.read()

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(raw)

    now = int(time.time())
    # Build map: stop_id -> [(eta_sec, direction_label, trip_id)]
    stop_arrivals = {}
    for ent in feed.entity:
        if not ent.HasField("trip_update"):
            continue
        for stu in ent.trip_update.stop_time_update:
            eta = stu.arrival.time if stu.HasField("arrival") and stu.arrival.time else \
                  (stu.departure.time if stu.HasField("departure") and stu.departure.time else 0)
            if not eta or eta < now:
                continue
            stop_arrivals.setdefault(stu.stop_id, []).append(eta - now)

    # Compose per-station payload we want to render
    stations_out = []
    for name, dirs in MTA_L_STATIONS.items():
        n_eta = sorted(stop_arrivals.get(dirs["N"], []))[:3]
        s_eta = sorted(stop_arrivals.get(dirs["S"], []))[:3]
        stations_out.append({
            "name": name,
            "manhattan_bound": [round(e / 60) for e in n_eta],   # minutes to arrival
            "canarsie_bound":  [round(e / 60) for e in s_eta],
        })
    return {"stations": stations_out, "fetched_at": now}


@app.route("/api/weather", methods=["GET"])
def api_weather():
    cached = _cache_get("weather")
    if cached:
        return jsonify({"ok": True, "data": cached, "cached": True})
    try:
        with _dash_lock:
            cached = _cache_get("weather")  # double-check under lock
            if cached:
                return jsonify({"ok": True, "data": cached, "cached": True})
            data = _fetch_weather()
            _cache_put("weather", data)
            return jsonify({"ok": True, "data": data, "cached": False})
    except Exception as e:
        LOG.error(f"Weather fetch failed: {e}")
        return jsonify({"ok": False, "error": str(e)}), 502


@app.route("/api/trains", methods=["GET"])
def api_trains():
    cached = _cache_get("trains")
    if cached:
        return jsonify({"ok": True, "data": cached, "cached": True})
    try:
        with _dash_lock:
            cached = _cache_get("trains")
            if cached:
                return jsonify({"ok": True, "data": cached, "cached": True})
            data = _fetch_mta_trains()
            _cache_put("trains", data)
            return jsonify({"ok": True, "data": data, "cached": False})
    except Exception as e:
        LOG.error(f"MTA fetch failed: {e}")
        return jsonify({"ok": False, "error": str(e)}), 502


@app.route("/dashboard")
def dashboard():
    """Serve the wall-mounted dashboard."""
    path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    if os.path.exists(path):
        return send_file(path)
    return "<h1>Dashboard</h1><p>dashboard.html not found</p>", 404


@app.route("/config", methods=["GET"])
def get_config():
    """Return current config, stations list, and discovered devices."""
    cfg = _load_config()
    return jsonify({
        "config": cfg,
        "stations": STATIONS,
        "discovered": _discovered,
    })


@app.route("/config", methods=["POST"])
def set_config():
    """Save configuration."""
    try:
        data = request.get_json()
        cfg = _load_config()

        # Update allowed fields
        for key in ["device_name", "station", "volume", "alarm_enabled",
                    "alarm_time", "alarm_days", "alarm_station", "custom_url",
                    "favorites"]:
            if key in data:
                cfg[key] = data[key]

        _save_config(cfg)
        return jsonify({"status": "ok", "config": cfg})
    except Exception as e:
        LOG.error(f"Error setting config: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/favorite", methods=["POST"])
def toggle_favorite():
    """Toggle a station in the favorites list."""
    try:
        data = request.get_json()
        station_id = data.get("station_id")
        if not station_id:
            return jsonify({"status": "error", "message": "Missing station_id"}), 400

        cfg = _load_config()
        favorites = cfg.get("favorites", [])

        if station_id in favorites:
            favorites.remove(station_id)
            action = "removed"
        else:
            favorites.append(station_id)
            action = "added"

        cfg["favorites"] = favorites
        _save_config(cfg)
        return jsonify({"status": "ok", "action": action, "favorites": favorites})
    except Exception as e:
        LOG.error(f"Error toggling favorite: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/play", methods=["POST"])
def play():
    """Play a station."""
    try:
        data = request.get_json()
        station_id = data.get("station_id")
        device_name = data.get("device_name")
        volume = data.get("volume", 50)
        custom_url = data.get("custom_url", "")

        if not station_id or not device_name:
            return jsonify({"status": "error", "message": "Missing station_id or device_name"}), 400

        success = play_station(station_id, device_name, volume, custom_url)
        return jsonify({"status": "ok" if success else "error"})
    except Exception as e:
        LOG.error(f"Error in /play: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/stop", methods=["POST"])
def stop():
    """Stop playback."""
    try:
        data = request.get_json()
        device_name = data.get("device_name")

        if not device_name:
            return jsonify({"status": "error", "message": "Missing device_name"}), 400

        success = stop_playback(device_name)
        return jsonify({"status": "ok" if success else "error"})
    except Exception as e:
        LOG.error(f"Error in /stop: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/volume", methods=["POST"])
def set_volume():
    """Set volume on device."""
    try:
        data = request.get_json()
        device_name = data.get("device_name")
        volume = data.get("volume", 50)

        if not device_name:
            return jsonify({"status": "error", "message": "Missing device_name"}), 400

        cast = _get_cast(device_name)
        if not cast:
            return jsonify({"status": "error", "message": f"Device '{device_name}' not found"}), 400

        # Normalize volume
        if isinstance(volume, float) and volume <= 1.0:
            volume = int(volume * 100)
        volume = max(0, min(100, int(volume)))
        # Skip if already at this level — prevents slider-drag from spamming
        # the Chromecast and keeps our cache accurate.
        if _cast_last_vol.get(device_name) != volume:
            cast.set_volume(volume / 100.0)
            _cast_last_vol[device_name] = volume
            _cast_last_ok[device_name] = time.monotonic()
        return jsonify({"status": "ok", "volume": volume})
    except Exception as e:
        LOG.error(f"Error setting volume: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/now-playing", methods=["GET"])
def now_playing():
    """Return what's currently playing."""
    with _play_lock:
        # Check if we're in grace period
        in_grace = time.time() < _stop_grace_until

        return jsonify({
            "station_id": _playing_station_id,
            "station_name": _playing_station_name,
            "device": _playing_device,
            "in_grace_period": in_grace,
        })


@app.route("/discover", methods=["GET"])
def discover():
    """Trigger mDNS discovery and return devices."""
    global _discovered

    try:
        LOG.info("Starting device discovery...")
        services, browser = pychromecast.discovery.discover_chromecasts(timeout=10)
        browser.stop_discovery()

        _discovered = []
        for svc in services:
            _discovered.append({
                "name": svc.friendly_name,
                "model": svc.model_name,
            })

        LOG.info(f"Discovered {len(_discovered)} devices")

        # Build cast objects and update cache
        if _discovered:
            chromecasts, _ = pychromecast.get_listed_chromecasts(
                friendly_names=[d["name"] for d in _discovered],
                discovery_timeout=5,
            )
            with _cast_lock:
                for cast in chromecasts:
                    _cast_cache[cast.name] = cast

        return jsonify({
            "status": "ok",
            "devices": _discovered,
        })
    except Exception as e:
        LOG.error(f"Error discovering devices: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400


# --- Startup ---

def _startup_discovery():
    """Run discovery at startup so speakers are available immediately."""
    import time
    time.sleep(1)  # Let Flask finish starting
    global _discovered
    try:
        LOG.info("Startup discovery: scanning for Chromecast devices...")
        services, browser = pychromecast.discovery.discover_chromecasts(timeout=8)
        browser.stop_discovery()
        _discovered = []
        for svc in services:
            _discovered.append({"name": svc.friendly_name, "model": svc.model_name})
        LOG.info(f"Startup discovery: found {len(_discovered)} devices")
        if _discovered:
            chromecasts, _ = pychromecast.get_listed_chromecasts(
                friendly_names=[d["name"] for d in _discovered],
                discovery_timeout=5,
            )
            with _cast_lock:
                for cast in chromecasts:
                    _cast_cache[cast.name] = cast
    except Exception as e:
        LOG.error(f"Startup discovery error: {e}")


if __name__ == "__main__":
    # Start alarm checking thread
    alarm_thread = threading.Thread(target=alarm_thread_worker, daemon=True)
    alarm_thread.start()
    LOG.info("Alarm thread started")

    # Start cast keep-alive thread — prevents stale-connection delays
    ka_thread = threading.Thread(target=cast_keepalive_worker, daemon=True)
    ka_thread.start()
    LOG.info("Cast keep-alive thread started")

    # Start background discovery
    disc_thread = threading.Thread(target=_startup_discovery, daemon=True)
    disc_thread.start()

    # Run Flask app
    app.run(host="0.0.0.0", port=8550, debug=False)

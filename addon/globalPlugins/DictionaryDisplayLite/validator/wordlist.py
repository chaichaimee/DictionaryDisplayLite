# wordlist.py

SAFE_LATIN_ABBREVIATIONS = frozenset(
	"AI IT UI EU US OK ID TV PC OS USB HD VR AR URL API".split()
)

_COMMON_ENGLISH = """
a about above across act actor add address after again against age ago agree air all allow almost alone along
already also always among amount and animal another answer any appear apple area arm around arrive art as ask at
away baby back bad bag ball bank base be beach bear beat beautiful because bed been before begin behind believe
below best better between big bird bit black blue board boat body book born both bottom box boy brain bread break
bring brother brown build burn business but buy by call came can car card care carry case cat catch cause center
century certain chair chance change check child choose city class clean clear close cloud coat cold color come
common company complete computer control cook cool copy corner cost could count country course cover create cross
crowd cry cut dance dark data day dead dear decide deep degree develop die different dinner direct do doctor dog
done door double down draw dream dress drink drive drop dry during each ear early earth east easy eat edge effect
egg eight either else end enemy engine enough enter equal even evening event ever every exact example except
expect eye face fact fall family far farm fast father fear feel feet few field fight figure fill final find fine
finger finish fire first fish five floor flow fly follow food foot for force foreign forest forget form forward
four free fresh friend from front fruit full fun game garden gas gave get girl give glad glass go gold gone good
got government grass great green ground group grow guess gun hair half hand happen happy hard has hat have he head
hear heart heat heavy held help her here high hill him his history hit hold hole home hope horse hot hour house
how huge human hundred hurry ice idea if image important in inch include instead into iron is island it its job
join joy jump just keep key kill kind king kitchen knew know lady lake land language large last late laugh law
lay lead learn least leave left leg length less let letter level library lie life lift light like line list
listen little live local long look lose lot loud love low machine made main make man many map mark market master
match matter may maybe me mean measure meat meet member men metal middle might mile milk million mind minute miss
modern moment money month moon more morning most mother mountain mouth move much music must my name nation near
need neighbor never new news next night nine no noise none noon nor north nose not note nothing notice now number
object ocean of off offer office often oil old on once one only open or order other our out over own page pain
paint pair paper parent part party pass past path pay peace people perhaps person phone pick picture piece place
plain plan plant play please point police poor popular position possible pound power present press pretty price
probably problem produce product program proper public pull push put quick quiet quite race radio rain raise ran
range rate reach read ready real reason record red remember rest result return rich ride right ring rise river
road rock room round rule run safe said sail salt same sand sat save saw say school science sea season seat second
see seem sell send sense sent serve set seven several shape share sharp she ship shoe shop short should shoulder
show side sign silent silver similar simple since sing single sister sit six size skin sky sleep slow small smell
smile snow so soft soil sold soldier some son song soon sort sound south space speak special speed spell spend
spoke spring square stand star start state station stay steel step still stone stop store story straight strange
street strong student study subject such sudden sugar summer sun supply sure surface surprise sweet swim system
table take talk tall teach team tell ten test than thank that the their them then there these they thick thin
thing think third this those though thought three through throw tie time tiny to today together told tomorrow
tone too took top total touch toward town trade train travel tree trip trouble true try turn two type under unit
until up upon us use usual valley value very village visit voice vote wait walk wall want war warm was wash watch
water wave way we wear weather week weight well went were west what wheel when where which while white who whole
whose why wide wife will wind window winter wish with without woman wonder wood word work world would write wrong
yard year yellow yes yet you young your zero zone
"""

_TECH_TERMS = """
api app apps audio bluetooth browser build bytes cache chrome click client cloud code config cookie copy cpu css
dark database debug desktop dll dns docker domain download driver drive email emoji excel facebook file firefox
firewall folder font frame github gmail google gpu hardware hdmi host html http https icon install instagram
internet java javascript json keyboard laptop line link linux login logout macos menu microsoft mouse network nvda
offline online open oracle outlook pdf phone pixel plugin podcast popup portable python reddit reset router
safari screen script server setup shell skype slack smartphone software speaker sql ssd stream switch tablet tag
telegram text thread tiktok toolbar twitter ubuntu update upload usb user video virtual wifi window windows
wireless word youtube zoom
"""

_MIXED_CASE_BRANDS = """
iphone ipad ipod macbook youtube facebook paypal javascript powerpoint whatsapp linkedin openai chatgpt github
gitlab airpods playstation
"""

ENGLISH_WORDS = frozenset(_COMMON_ENGLISH.split())
TECH_WORDS = frozenset(_TECH_TERMS.split())
MIXED_CASE_ALLOWED = frozenset(_MIXED_CASE_BRANDS.split())
KNOWN_WORDS = ENGLISH_WORDS | TECH_WORDS

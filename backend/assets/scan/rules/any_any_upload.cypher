MATCH
  (sinkNode:Call)
WHERE
  sinkNode.AllocationClassName IN ['FileOutputStream', 'FileWriter', 'BufferedOutputStream'] OR
  (
    (sinkNode.selector = 'transferTo' OR 'transferTo' IN coalesce(sinkNode.selectors, [])) AND
    (
      (sinkNode.type IS NOT NULL AND (sinkNode.type = 'MultipartFile' OR sinkNode.type ENDS WITH '.MultipartFile')) OR
      any(t IN coalesce(sinkNode.receiverTypes, []) WHERE t = 'MultipartFile' OR t ENDS WITH '.MultipartFile')
    )
  ) OR
  (
    'write' IN coalesce(sinkNode.selectors, []) AND
    any(t IN coalesce(sinkNode.receiverTypes, []) WHERE t IN ['FileItem', 'org.apache.commons.fileupload.FileItem'])
  ) OR
  (
    'write' IN coalesce(sinkNode.selectors, []) AND
    any(t IN coalesce(sinkNode.receiverTypes, []) WHERE t IN ['Files', 'java.nio.file.Files'])
  ) OR
  (
    'copy' IN coalesce(sinkNode.selectors, []) AND
    any(t IN coalesce(sinkNode.receiverTypes, []) WHERE t IN ['Files', 'java.nio.file.Files'])
  ) OR
  (
    'copyInputStreamToFile' IN coalesce(sinkNode.selectors, []) AND
    any(t IN coalesce(sinkNode.receiverTypes, []) WHERE t IN ['FileUtils', 'org.apache.commons.io.FileUtils'])
  ) OR
  (
    'writeByteArrayToFile' IN coalesce(sinkNode.selectors, []) AND
    any(t IN coalesce(sinkNode.receiverTypes, []) WHERE t IN ['FileUtils', 'org.apache.commons.io.FileUtils'])
  ) OR
  (
    'toFile' IN coalesce(sinkNode.selectors, []) AND
    any(t IN coalesce(sinkNode.receiverTypes, []) WHERE t IN ['ByteSource', 'com.google.common.io.ByteSource'])
  ) OR
  (
    'uploadFile' IN coalesce(sinkNode.selectors, []) AND
    any(t IN coalesce(sinkNode.receiverTypes, []) WHERE t IN ['FileUploadService'])
  ) OR
  (
    'save' IN coalesce(sinkNode.selectors, []) AND
    any(t IN coalesce(sinkNode.receiverTypes, []) WHERE t IN ['StorageService'])
  ) OR
  (
    'handleFileUpload' IN coalesce(sinkNode.selectors, []) AND
    any(t IN coalesce(sinkNode.receiverTypes, []) WHERE t IN ['UploadController'])
  )

MATCH
  (argNode)-[argRel:ARG]->(sinkNode)
WHERE
  coalesce(argRel.argIndex, -1) >= 0 AND
  NOT 'Lit' IN labels(argNode)

MATCH
  (sourceNode)-[:ARG|REF|CALLS|HAS_CALL*1..8]->(argNode)
WHERE
  (
    sourceNode:DubboServiceArg OR
    sourceNode:JsfXhtmlArg OR
    sourceNode:JaxwsArg OR
    sourceNode:StrutsActionArg OR
    sourceNode:ThriftHandlerArg OR
    sourceNode:NettyHandlerArg OR
    sourceNode:JfinalControllerArg OR
    sourceNode:JbootControllerArg OR
    sourceNode:SpringControllerArg OR
    sourceNode:SolonControllerArg OR
    sourceNode:SpringInterceptorArg OR
    sourceNode:JspServiceArg OR
    sourceNode:WebServletArg OR
    sourceNode:WebXmlServletArg OR
    sourceNode:WebXmlFilterArg OR
    sourceNode:JaxrsArg OR
    sourceNode:HttpHandlerArg
  ) AND
  coalesce(sourceNode.name, '') <> 'this' AND
  NOT sourceNode.type IN ['Long', 'Integer', 'int', 'long', 'boolean', 'Boolean', 'HttpServletResponse']

MATCH
  p = shortestPath((sourceNode)-[:ARG|REF|CALLS|HAS_CALL*1..16]->(sinkNode))
WHERE
  NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer', 'int', 'long'])
WITH sourceNode, sinkNode, p
ORDER BY length(p) ASC
WITH
  coalesce(sourceNode.id, toString(id(sourceNode))) AS sId,
  coalesce(sinkNode.id, toString(id(sinkNode))) AS tId,
  collect(p)[0] AS path
RETURN
  path AS path

/*
Chanzi-Separator

鏂囦欢涓婁紶婕忔礊

鏂囦欢涓婁紶鍩烘湰鍘熺悊娑夊強鍒癢eb搴旂敤绋嬪簭濡備綍澶勭悊鐢ㄦ埛涓婁紶鐨勬枃浠躲€備互涓嬫槸杩欎竴婕忔礊鐨勫叧閿偣锛?

鐢ㄦ埛涓婁紶鎺ュ彛锛歐eb搴旂敤绋嬪簭閫氬父鍖呭惈涓婁紶鏂囦欢鐨勫姛鑳斤紝鍏佽鐢ㄦ埛灏嗘枃浠讹紙濡傚浘鐗囥€佹枃妗ｇ瓑锛変笂浼犲埌鏈嶅姟鍣ㄣ€?

杈撳叆楠岃瘉涓嶈冻锛氬鏋滃簲鐢ㄧ▼搴忔湭鑳藉厖鍒嗛獙璇佺敤鎴蜂笂浼犵殑鏂囦欢绫诲瀷鍜屽唴瀹癸紝灏卞彲鑳藉厑璁告伓鎰忔枃浠朵笂浼犮€?

鏂囦欢绫诲瀷杩囨护锛氬簲鐢ㄧ▼搴忓彲鑳介€氳繃妫€鏌ユ枃浠舵墿灞曞悕鎴朚IME绫诲瀷鏉ラ檺鍒跺厑璁镐笂浼犵殑鏂囦欢绫诲瀷銆傜劧鑰岋紝杩欑鏂规硶涓嶅畨鍏紝鍥犱负鎵╁睍鍚嶅拰MIME绫诲瀷鍙互琚吉閫犮€?

鎵ц鏉冮檺锛氬鏋滀笂浼犵殑鏂囦欢锛堢壒鍒槸鑴氭湰鎴栧彲鎵ц鏂囦欢锛夎鏀剧疆鍦ㄥ叿鏈夋墽琛屾潈闄愮殑鐩綍涓紝瀹冧滑鍙兘琚玏eb鏈嶅姟鍣ㄦ墽琛屻€?

璺緞閬嶅巻锛氭敾鍑昏€呭彲鑳藉皾璇曢€氳繃鍦ㄦ枃浠跺悕涓娇鐢ㄧ壒娈婂瓧绗︼紙濡?./锛夋潵璁块棶鏈嶅姟鍣ㄤ笂鐨勫叾浠栫洰褰曞拰鏂囦欢銆?

鏈嶅姟绔В鏋愭紡娲烇細鏌愪簺Web鏈嶅姟鍣ㄦ垨搴旂敤绋嬪簭鍙兘瀛樺湪瑙ｆ瀽婕忔礊锛屽厑璁稿鐗瑰畾绫诲瀷鐨勬枃浠惰繘琛岄敊璇殑瑙ｉ噴锛屼緥濡傚皢涓€涓湅璧锋潵鍍忓浘鐗囩殑鏂囦欢瑙ｆ瀽涓哄彲鎵ц鑴氭湰銆?

鏂囦欢鍖呭惈婕忔礊锛氬鏋滃簲鐢ㄧ▼搴忎娇鐢ㄧ敤鎴峰彲鎺х殑杈撳叆鏉ュ寘鍚枃浠讹紝鏀诲嚮鑰呭彲鑳藉埄鐢ㄨ繖涓€鐐规潵鍖呭惈骞舵墽琛屼笂浼犵殑鎭舵剰鏂囦欢銆?

瀛樺偍浣嶇疆锛氬鏋滀笂浼犵殑鏂囦欢瀛樺偍鍦╓eb鏍圭洰褰曟垨鍙叕寮€璁块棶鐨勪綅缃紝鏀诲嚮鑰呭彲鑳界洿鎺ラ€氳繃URL璁块棶杩欎簺鏂囦欢銆?

璁块棶鎺у埗锛氬簲鐢ㄧ▼搴忓彲鑳芥湭鑳芥纭疄鏂借闂帶鍒讹紝鍏佽鏈粡鎺堟潈鐨勭敤鎴疯闂垨鎵ц涓婁紶鐨勬枃浠躲€?

瀹夊叏閰嶇疆锛歐eb鏈嶅姟鍣ㄦ垨搴旂敤绋嬪簭鐨勪笉瀹夊叏閰嶇疆鍙兘澧炲姞鏂囦欢涓婁紶婕忔礊鐨勯闄┿€?


Chanzi-Separator

淇Java涓枃浠朵笂浼犳紡娲為渶瑕侀噰鍙栦竴绯诲垪瀹夊叏鎺柦鏉ョ‘淇濅笂浼犵殑鏂囦欢涓嶄細瀵规湇鍔″櫒瀹夊叏閫犳垚濞佽儊銆備互涓嬫槸涓€浜涘叧閿殑淇寤鸿锛?

浣跨敤鐧藉悕鍗曪細浠呭厑璁哥壒瀹氱被鍨嬬殑鏂囦欢涓婁紶锛屽鍥剧墖鍜屾枃妗ｏ紝骞剁‘淇濊繖浜涚被鍨嬩笉鍙兘琚墽琛屻€?

闄愬埗鏂囦欢瑙ｆ瀽锛氬浜庣敤鎴蜂笂浼犵殑鏂囦欢锛屽啀娆￠€氳繃 url 璁块棶璇ユ枃浠舵椂锛岀洿鎺ヤ互鏂囦欢涓嬭浇鏂瑰紡杩斿洖锛屽嵆浣夸笂浼犱簡 html銆乯sp涔熶笉杩涜瑙ｆ瀽銆?

鏂囦欢绫诲瀷楠岃瘉锛氬湪鏈嶅姟鍣ㄧ楠岃瘉鏂囦欢鐨凪IME绫诲瀷锛岀‘淇濅笂浼犵殑鏂囦欢涓庢墍澹版槑鐨勭被鍨嬬浉绗︺€?

鏂囦欢鎵╁睍鍚嶆鏌ワ細妫€鏌ユ枃浠舵墿灞曞悕鏄惁鍦ㄥ厑璁哥殑鍒楄〃涓紝浣嗚娉ㄦ剰杩欏苟涓嶈冻浠ラ槻姝㈡敾鍑伙紝鍥犱负鎵╁睍鍚嶅彲浠ヨ浼€犮€?

鍐呭妫€鏌ワ細瀵逛笂浼犵殑鏂囦欢杩涜鎵弿锛屾煡鎵惧彲鑳界殑鎭舵剰浠ｇ爜锛岀壒鍒槸瀵逛簬鑴氭湰鍜屽彲鎵ц鏂囦欢銆?

闅忔満閲嶅懡鍚嶆枃浠讹細鏇存敼涓婁紶鏂囦欢鐨勫悕绉帮紝浣跨敤闅忔満鐢熸垚鐨勫悕绉帮紝浠ラ槻姝㈤鏈熺殑鏂囦欢鍚嶆敾鍑汇€?

闄愬埗鏂囦欢澶у皬锛氳缃枃浠跺ぇ灏忛檺鍒讹紝闃叉杩囧ぇ鐨勬枃浠朵笂浼犳秷鑰楁湇鍔″櫒璧勬簮鎴栧埄鐢ㄦ綔鍦ㄧ殑婕忔礊銆?

鏂囦欢涓婁紶鐩綍鏉冮檺锛氱‘淇濇枃浠朵笂浼犵洰褰曚笉鍏佽鎵ц鏉冮檺锛岃繖鏍峰嵆浣夸笂浼犱簡鑴氭湰鏂囦欢锛屼篃鏃犳硶琚湇鍔″櫒鎵ц銆?

浣跨敤瀹夊叏鐨勬枃浠跺鐞嗗簱锛氫娇鐢ㄦ垚鐔熺殑鏂囦欢澶勭悊搴撴潵澶勭悊涓婁紶鐨勬枃浠讹紝閬垮厤鑷繁澶勭悊鏂囦欢涓婁紶鏃跺彲鑳藉紩鍏ョ殑瀹夊叏椋庨櫓銆?

鍓嶇鍜屽悗绔獙璇侊細鍦ㄥ墠绔拰鍚庣閮借繘琛屾枃浠堕獙璇侊紝纭繚鍗充娇鍓嶇楠岃瘉琚粫杩囷紝鍚庣涔熻兘鎻愪緵瀹夊叏淇濋殰銆?

閬垮厤浣跨敤../锛氱‘淇濇枃浠朵笂浼犺矾寰勪笉鍖呭惈../锛岄槻姝㈡敾鍑昏€呴€氳繃璺緞閬嶅巻璁块棶鍏朵粬鐩綍銆?

浣跨敤HTTPS锛氶€氳繃浣跨敤HTTPS鏉ヤ笂浼犳枃浠讹紝纭繚鏂囦欢鍦ㄤ紶杈撹繃绋嬩腑鐨勫畨鍏ㄦ€э紝闃叉涓棿浜烘敾鍑汇€?

閿欒娑堟伅澶勭悊锛氶伩鍏嶅湪閿欒娑堟伅涓樉绀烘晱鎰熶俊鎭紝濡傛枃浠惰矾寰勬垨鏈嶅姟鍣ㄩ厤缃€?

Chanzi-Separator
*/

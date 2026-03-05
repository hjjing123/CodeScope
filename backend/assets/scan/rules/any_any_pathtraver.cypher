MATCH
  (sourceNode)
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
    NOT sourceNode.type  IN ['Long', 'Integer', 'HttpServletResponse']


MATCH
  (sinkNode)
  WHERE
  // Path-sensitive file access sinks (generic, avoids method-context-only hits)
  ('openStream' IN sinkNode.selectors AND 'File' IN sinkNode.receiverTypes) OR
  ('newInputStream' IN sinkNode.selectors AND 'File' IN sinkNode.receiverTypes) OR
  ('toByteArray' IN sinkNode.selectors AND 'Files' IN sinkNode.receiverTypes) OR
  ('readAllLines' IN sinkNode.selectors AND 'Files' IN sinkNode.receiverTypes) OR
  ('readAllBytes' IN sinkNode.selectors AND 'Files' IN sinkNode.receiverTypes) OR
  ('readString' IN sinkNode.selectors AND 'Files' IN sinkNode.receiverTypes) OR
  ('newInputStream' IN sinkNode.selectors AND 'Files' IN sinkNode.receiverTypes) OR
  ('walk' IN sinkNode.selectors AND 'Files' IN sinkNode.receiverTypes) OR
  ('list' IN sinkNode.selectors AND 'Files' IN sinkNode.receiverTypes) OR
  ('readToString' IN sinkNode.selectors AND 'FileUtils' IN sinkNode.receiverTypes) OR
  ('readLines' IN sinkNode.selectors AND 'FileUtils' IN sinkNode.receiverTypes) OR
  ('readFileToByteArray' IN sinkNode.selectors AND 'FileUtils' IN sinkNode.receiverTypes) OR
  ('contentEquals' IN sinkNode.selectors AND 'FileUtils' IN sinkNode.receiverTypes) OR
  ('listFiles' IN sinkNode.selectors AND 'FileUtils' IN sinkNode.receiverTypes) OR
  ('toString' IN sinkNode.selectors AND 'IOUtils' IN sinkNode.receiverTypes) OR
  ('toByteArray' IN sinkNode.selectors AND 'IOUtils' IN sinkNode.receiverTypes) OR
  ('readLines' IN sinkNode.selectors AND 'IOUtils' IN sinkNode.receiverTypes) OR
  ('copy' IN sinkNode.selectors AND 'IOUtils' IN sinkNode.receiverTypes) OR
  ('getResourceAsStream' IN sinkNode.selectors AND 'ResourceLoader' IN sinkNode.receiverTypes) OR
  ('getFile' IN sinkNode.selectors AND 'Resource' IN sinkNode.receiverTypes) OR
  ('read' IN sinkNode.selectors AND 'FileSystemResource' IN sinkNode.receiverTypes) OR
  ('exists' IN sinkNode.selectors AND 'File' IN sinkNode.receiverTypes) OR
  ('isFile' IN sinkNode.selectors AND 'File' IN sinkNode.receiverTypes) OR
  ('isDirectory' IN sinkNode.selectors AND 'File' IN sinkNode.receiverTypes) OR
  ('listFiles' IN sinkNode.selectors AND 'File' IN sinkNode.receiverTypes) OR
  ('length' IN sinkNode.selectors AND 'File' IN sinkNode.receiverTypes) OR
  ('getCanonicalPath' IN sinkNode.selectors AND 'File' IN sinkNode.receiverTypes)

MATCH
  p = shortestPath((sourceNode)-[:ARG|REF|CALLS*..12]->(sinkNode))
  WHERE none(n IN nodes(p)
    WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer', 'int', 'long'])
RETURN
  DISTINCT p AS path


/*
Chanzi-Separator

鐩綍绌胯秺

Java涓殑鐩綍绌胯秺婕忔礊锛岄€氬父涔熺О涓鸿矾寰勭┛瓒婃紡娲烇紙Path Traversal锛夛紝鏄竴绉嶅畨鍏ㄦ紡娲烇紝瀹冨厑璁告敾鍑昏€呴€氳繃搴旂敤绋嬪簭鐨勮緭鍏ユ帴鍙ｈ闂垨鎿嶄綔搴旂敤绋嬪簭鏂囦欢绯荤粺涓婄殑闈為鏈熸枃浠跺拰鐩綍銆備互涓嬫槸鐩綍绌胯秺婕忔礊鐨勫師鐞嗭細

杈撳叆鎺ュ彛锛氭紡娲為€氬父鍙戠敓鍦ㄥ簲鐢ㄧ▼搴忔帴鍙楃敤鎴疯緭鍏ヤ綔涓烘枃浠惰矾寰勬垨鍚嶇О鐨勫湴鏂广€?

杈撳叆鏈繃婊ゆ垨鏈纭鐞嗭細濡傛灉搴旂敤绋嬪簭鏈兘瀵圭敤鎴疯緭鍏ヨ繘琛岄€傚綋鐨勮繃婊ゆ垨澶勭悊锛屾敾鍑昏€呭氨鍙兘鎻愪氦鐗规畩鏋勯€犵殑杈撳叆鏉ュ埄鐢ㄨ婕忔礊銆?

璺緞瑙ｆ瀽婕忔礊锛氭敾鍑昏€呭埄鐢ㄦ枃浠剁郴缁熻矾寰勮В鏋愮殑婕忔礊锛岄€氳繃杈撳叆濡?./锛堢埗鐩綍锛夌殑搴忓垪鏉ヤ笂鍗囩洰褰曞眰娆＄粨鏋勩€?

璁块棶鎺у埗缁曡繃锛氶€氳繃鐩綍绌胯秺锛屾敾鍑昏€呭彲鑳界粫杩囧簲鐢ㄧ▼搴忕殑璁块棶鎺у埗鏈哄埗锛岃闂彈闄愮洰褰曟垨鏂囦欢銆?

鏂囦欢娉勯湶锛氭敾鍑昏€呭彲鑳藉埄鐢ㄦ婕忔礊鏉ヤ笅杞芥垨鏌ョ湅搴旂敤绋嬪簭鐨勯厤缃枃浠躲€佹簮浠ｇ爜銆佹晱鎰熸暟鎹瓑銆?

鏂囦欢鎿嶄綔锛氬湪鏌愪簺鎯呭喌涓嬶紝鏀诲嚮鑰呭彲鑳戒笉浠呰兘澶熻闂枃浠讹紝杩樿兘澶熶慨鏀规垨鍒犻櫎瀹冧滑銆?

Web搴旂敤绋嬪簭涓殑浣撶幇锛氬湪Web搴旂敤绋嬪簭涓紝鐩綍绌胯秺婕忔礊鍙兘閫氳繃URL鍙傛暟銆佽〃鍗曞瓧娈垫垨鍏朵粬HTTP璇锋眰閮ㄥ垎浼犻€掔殑杈撳叆鍙傛暟鏉ヨЕ鍙戙€?

Chanzi-Separator

杈撳叆楠岃瘉锛氬鎵€鏈夌敤鎴疯緭鍏ヨ繘琛屼弗鏍肩殑楠岃瘉锛岀‘淇濆畠浠笉鍖呭惈娼滃湪鐨勫嵄闄╁瓧绗︽垨妯″紡锛屽..銆?銆乗绛夈€?

璺緞瑙勮寖鍖栵細鍦ㄥ鐞嗕换浣曠敤鎴疯緭鍏ョ殑鏂囦欢璺緞涔嬪墠锛屼娇鐢↗ava鐨刯ava.nio.file.Paths.get()鏂规硶鎴栫浉浼肩殑搴撳嚱鏁板鍏惰繘琛岃鑼冨寲锛屼互娑堥櫎浠讳綍鐩稿璺緞缁勪欢銆?

浣跨敤鐧藉悕鍗曪細瀵逛簬鍏佽鐢ㄦ埛涓婁紶鎴栦笅杞界殑鏂囦欢绫诲瀷鍜屾墿灞曞悕锛屼娇鐢ㄧ櫧鍚嶅崟楠岃瘉鏂规硶鏉ラ檺鍒剁敤鎴疯緭鍏ャ€?

缁濆璺緞锛氭€绘槸浣跨敤缁濆璺緞鏉ヨ闂枃浠剁郴缁熻祫婧愶紝閬垮厤浣跨敤鐩稿璺緞銆?

闄愬埗鏂囦欢璁块棶鑼冨洿锛氱‘淇濆簲鐢ㄧ▼搴忕殑鏂囦欢鎿嶄綔琚檺鍒跺湪鐗瑰畾鐨勭洰褰曞唴锛屼笉鍏佽璁块棶璇ョ洰褰曚箣澶栫殑鏂囦欢銆?

閬垮厤浣跨敤鐢ㄦ埛杈撳叆浣滀负璺緞锛氬鏋滃彲鑳斤紝涓嶈鐩存帴浣跨敤鐢ㄦ埛杈撳叆浣滀负鏂囦欢璺緞锛屽彲浠ヨ€冭檻浣跨敤鏂囦欢id绛変唬鏇跨洿鎺ヨ緭鍏ヨ矾寰勩€?

鏂囦欢鏉冮檺锛氫负搴旂敤绋嬪簭杩愯鐨勮处鎴疯缃€傚綋鐨勬枃浠舵潈闄愶紝纭繚瀹冧滑鍙兘璁块棶蹇呰鐨勬枃浠跺拰鐩綍銆?

閿欒澶勭悊锛氬湪閿欒澶勭悊涓伩鍏嶆硠闇叉枃浠剁郴缁熺粨鏋勪俊鎭紝纭繚閿欒娑堟伅涓嶄細鏆撮湶搴旂敤绋嬪簭鐨勫唴閮ㄦ枃浠惰矾寰勩€?

浣跨敤瀹夊叏鐨凙PI锛氫娇鐢↗ava鎻愪緵鐨勫畨鍏ㄧ殑鏂囦欢鎿嶄綔API锛岄伩鍏嶄娇鐢ㄥ彲鑳藉鏄撳彈鍒扮洰褰曠┛瓒婃敾鍑荤殑鏃PI銆?

浣跨敤鏂囦欢鍚嶅搱甯岋細瀵逛簬涓婁紶鐨勬枃浠讹紝浣跨敤鍝堝笇鍑芥暟鐢熸垚鏂扮殑鏂囦欢鍚嶏紝閬垮厤浣跨敤鐢ㄦ埛鎸囧畾鐨勬枃浠跺悕銆?

閬垮厤璺緞鎷兼帴锛氶伩鍏嶄娇鐢ㄥ瓧绗︿覆鎷兼帴鏉ユ瀯寤烘枃浠惰矾寰勶紝杩欏彲鑳藉鏄撳嚭閿欏苟瀵艰嚧瀹夊叏婕忔礊銆?

妫€鏌ユ枃浠跺瓨鍦ㄦ€э細鍦ㄥ厑璁告枃浠惰闂箣鍓嶏紝妫€鏌ユ枃浠舵槸鍚﹀瓨鍦紝閬垮厤鏀诲嚮鑰呴€氳繃鎸囧畾涓嶅瓨鍦ㄧ殑鏂囦欢鏉ョ粫杩囨鏌ャ€?

浣跨敤瀹夊叏鐨勯厤缃細纭繚搴旂敤绋嬪簭鐨勯厤缃枃浠朵笉鍖呭惈纭紪鐮佺殑鏂囦欢璺緞锛屾垨鑰呭鏋滃繀椤诲寘鍚紝纭繚瀹冧滑鏄畨鍏ㄧ殑銆?

Chanzi-Separator
*/

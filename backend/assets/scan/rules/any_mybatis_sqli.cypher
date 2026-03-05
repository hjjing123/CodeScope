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
  coalesce(sourceNode.name, '') <> 'this' AND
  NOT sourceNode.type IN ['Long', 'Integer', 'Boolean', 'HttpServletResponse']

MATCH
  (sinkNode:Call:MybatisMethodArg)
WHERE
  coalesce(sinkNode.selector, '') <> '' AND
  (
    toLower(coalesce(sinkNode.methodFullName, '')) CONTAINS '.mapper.' OR
    any(rt IN coalesce(sinkNode.receiverTypes, []) WHERE toLower(rt) CONTAINS 'mapper') OR
    any(rc IN coalesce(sinkNode.receivers, []) WHERE toLower(rc) CONTAINS 'mapper')
  ) AND
  (
    any(lb IN labels(sinkNode) WHERE lb IN ['MybatisAnnotationUnsafeArg', 'MybatisXmlUnsafeArg']) OR
    exists {
      MATCH (xml:XmlElement)
      WHERE
        toLower(coalesce(xml.name, '')) IN ['select', 'insert', 'update', 'delete'] AND
        coalesce(xml.code, '') CONTAINS '${' AND
        toLower(coalesce(xml.code, '')) CONTAINS ('id="' + toLower(coalesce(sinkNode.selector, '')) + '"')
    } OR
    toLower(coalesce(sinkNode.selector, '')) =~ '.*(order|sort|column|field|table|sql|expr|where|clause|raw|query|search).*'
  )

MATCH
  p = shortestPath((sourceNode)-[:ARG|REF|CALLS|HAS_CALL*1..12]->(sinkNode))
WHERE
  NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer', 'int', 'long']) AND
  EXISTS {
    MATCH (argNode)-[argRel:ARG]->(sinkNode)
    WHERE
      coalesce(argRel.argIndex, -1) > 0 AND
      NOT 'Lit' IN labels(argNode) AND
      (sourceNode)-[:ARG|REF|CALLS|HAS_CALL*1..6]->(argNode)
  }
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

mybatis sql娉ㄥ叆

鍦ㄤ娇鐢∕yBatis鏃讹紝SQL娉ㄥ叆婕忔礊鐨勪骇鐢熷師鐞嗕笌鐩存帴浣跨敤JDBC鎴朖PA鏃剁被浼硷紝涓昏鏄洜涓哄簲鐢ㄧ▼搴忔湭鑳芥纭鐞嗙敤鎴疯緭鍏ワ紝瀵艰嚧鏀诲嚮鑰呰兘澶熷湪SQL璇彞涓敞鍏ユ伓鎰忎唬鐮併€備互涓嬫槸MyBatis涓骇鐢烻QL娉ㄥ叆婕忔礊鐨勫師鐞嗭細

鍔ㄦ€丼QL锛歁yBatis鏀寔鍔ㄦ€丼QL锛屽厑璁告牴鎹潯浠跺姩鎬佸湴鎷兼帴SQL璇彞銆傚鏋滆繖浜涙潯浠朵腑鍖呭惈浜嗘湭缁忚繃婊ゆ垨鏈粡楠岃瘉鐨勭敤鎴疯緭鍏ワ紝灏卞彲鑳借鏀诲嚮鑰呭埄鐢ㄣ€?

鐢ㄦ埛杈撳叆鎷兼帴锛氬鏋滅敤鎴疯緭鍏ヨ鐩存帴鎷兼帴鍒癝QL璇彞涓紝鑰屼笉鏄綔涓哄弬鏁颁紶閫掞紝鏀诲嚮鑰呭彲浠ラ€氳繃鏋勯€犵壒娈婅緭鍏ユ潵娉ㄥ叆鎭舵剰SQL浠ｇ爜銆?

MyBatis鐨勮剼鏈姛鑳斤細MyBatis鍏佽鍦╔ML鏄犲皠鏂囦欢鎴栨敞瑙ｄ腑浣跨敤鑴氭湰璇█锛堝JavaScript锛夛紝濡傛灉鐢ㄦ埛鑳藉鎺у埗鑴氭湰涓殑杈撳叆锛屽氨鍙兘浜х敓娉ㄥ叆椋庨櫓銆?

XML鏄犲皠鏂囦欢鐨勯厤缃細濡傛灉MyBatis鐨刋ML鏄犲皠鏂囦欢鎴栨敞瑙ｈ閰嶇疆涓虹洿鎺ュ寘鍚敤鎴疯緭鍏ワ紝鑰屼笉鏄娇鐢ㄩ缂栬瘧鐨凷QL璇彞鎴栧弬鏁板寲鏌ヨ锛屽氨鍙兘浜х敓SQL娉ㄥ叆婕忔礊銆?

缂轰箯杈撳叆楠岃瘉锛氬簲鐢ㄧ▼搴忔湭鑳藉鐢ㄦ埛杈撳叆杩涜閫傚綋鐨勯獙璇佸拰杩囨护锛屽厑璁告敾鍑昏€呮彁浜ょ壒娈婃瀯閫犵殑杈撳叆銆?

MyBatis鐨勫姩鎬佽瑷€鏀寔锛歁yBatis鐨勫姩鎬丼QL鍔熻兘锛屽 script 鏍囩锛屽厑璁告墽琛屽鏉傜殑鍔ㄦ€丼QL璇彞銆傚鏋滆繖浜涜鍙ヤ腑鍖呭惈浜嗙敤鎴疯緭鍏ワ紝灏卞彲鑳借鍒╃敤鏉ユ墽琛孲QL娉ㄥ叆銆?

鏁版嵁搴撴潈闄愶細濡傛灉搴旂敤绋嬪簭浣跨敤鐨勬暟鎹簱璐︽埛鍏锋湁杈冮珮鐨勬潈闄愶紝SQL娉ㄥ叆婕忔礊鐨勫奖鍝嶅彲鑳戒細鏇村姞涓ラ噸銆?

MyBatis閰嶇疆涓嶅綋锛歁yBatis閰嶇疆涓嶅綋锛屽鍏佽鍔ㄦ€佺敓鎴怱QL璇彞鑰屾病鏈夐€傚綋鐨勫畨鍏ㄦ帾鏂斤紝涔熷彲鑳藉鍔燬QL娉ㄥ叆鐨勯闄┿€?


Chanzi-Separator

鍦ㄤ娇鐢∕yBatis鏃讹紝涓轰簡闃叉SQL娉ㄥ叆婕忔礊锛屽彲浠ラ噰鍙栦互涓嬩慨澶嶅缓璁細

浣跨敤棰勭紪璇戣鍙ワ細MyBatis鏀寔棰勭紪璇戣鍙ワ紝纭繚浣跨敤鍙傛暟鍖栨煡璇㈣€屼笉鏄瓧绗︿覆鎷兼帴鏉ユ瀯寤篠QL璇彞銆?

閬垮厤鍔ㄦ€丼QL鎷兼帴锛氫笉瑕佸湪MyBatis鐨刋ML鏄犲皠鏂囦欢鎴栨敞瑙ｄ腑鐩存帴浣跨敤鐢ㄦ埛杈撳叆鎷兼帴SQL璇彞銆?

杈撳叆楠岃瘉锛氬鎵€鏈夌敤鎴疯緭鍏ヨ繘琛屼弗鏍肩殑楠岃瘉锛岀‘淇濆畠浠鍚堥鏈熸牸寮忥紝閬垮厤鎭舵剰杈撳叆銆?

浣跨敤MyBatis鐨勫姩鎬丼QL鐗规€э細MyBatis鎻愪緵浜?{}鍜?{}浣滀负鍙傛暟鍗犱綅绗︺€傚缁堜娇鐢?{}鏉ラ槻姝QL娉ㄥ叆锛屽洜涓哄畠浼氬皢杈撳叆杞箟锛涜€?{}鍒欓渶瑕佽皑鎱庝娇鐢紝鍥犱负瀹冧細鐩存帴灏嗗唴瀹规彃鍏QL璇彞銆?

鏈€灏忓寲鏉冮檺锛氱‘淇濆簲鐢ㄧ▼搴忎娇鐢ㄧ殑鏁版嵁搴撹处鎴峰叿鏈夋墽琛屽繀瑕佹搷浣滅殑鏈€灏忔潈闄愩€?

浣跨敤Type Handlers锛歁yBatis鍏佽鑷畾涔塗ype Handlers鏉ュ鐞嗚緭鍏ュ拰杈撳嚭鐨勮浆鎹紝纭繚杩欎簺澶勭悊鍣ㄦ槸瀹夊叏鐨勩€?

閿欒澶勭悊锛氱‘淇濋敊璇鐞嗕笉浼氬悜鐢ㄦ埛灞曠ず鏁忔劅鐨凷QL閿欒淇℃伅銆?

鏇存柊鍜岃ˉ涓侊細淇濇寔MyBatis鍜屾暟鎹簱椹卞姩绋嬪簭鐨勬洿鏂帮紝搴旂敤瀹夊叏琛ヤ竵鏉ヤ慨澶嶅凡鐭ョ殑瀹夊叏婕忔礊銆?

浣跨敤MyBatis鐨勬彃浠舵満鍒讹細MyBatis鍏佽浣跨敤鎻掍欢鏉ユ嫤鎴拰澶勭悊SQL璇彞锛屽彲浠ュ紑鍙戣嚜瀹氫箟鎻掍欢鏉ユ娴嬪拰闃叉SQL娉ㄥ叆銆?

浣跨敤鐧藉悕鍗曪細瀵逛簬杈撳叆搴旈檺鍒朵负棰勫畾涔夌殑閫夐」鎴栧€硷紝浣跨敤鐧藉悕鍗曢獙璇佹柟娉曟潵闄愬埗鐢ㄦ埛杈撳叆銆?

Chanzi-Separator
*/


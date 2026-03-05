MATCH
  (sourceNode)
WHERE
  (
    // jfinal : String keyword=this.getPara("keyword");
    (sourceNode:CallArg AND 'getPara' IN sourceNode.selectors) OR
    sourceNode.assignRight STARTS WITH 'getParamsMap' OR
    sourceNode.assignRight STARTS WITH 'getParaMap' OR
    // 涓€浜涙鏋惰嚜瀹氫箟娉ㄨВ锛?璇锋眰鍏ュ弬浣跨敤 @HttpParam
    (sourceNode:MethodBinding AND 'HttpParam' IN sourceNode.paramAnnotations)
  ) AND
  coalesce(sourceNode.name, '') <> 'this' AND
  NOT sourceNode.type IN ['Long', 'Integer', 'HttpServletResponse']

MATCH
  (sinkNode:Call)
WHERE
  ('merge' IN sinkNode.selectors AND 'template' IN sinkNode.receivers) OR
  ('merge' IN sinkNode.selectors AND 'Template' IN sinkNode.receiverTypes)

MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
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

Velocity xss

Velocity 鏄竴绉嶆ā鏉垮紩鎿庯細瀹冧富瑕佺敤浜庡皢鏁版嵁涓庢ā鏉跨浉缁撳悎鐢熸垚鍔ㄦ€佺殑鏂囨湰杈撳嚭锛屽父鐢ㄤ簬 Web 寮€鍙戜腑銆備緥濡傦紝鍦?Java 寮€鍙戠殑 Web 搴旂敤涓紝Velocity 鍙互灏嗗悗鍙扮殑鏁版嵁濉厖鍒?HTML 妯℃澘涓紝鐢熸垚鏈€缁堝憟鐜扮粰鐢ㄦ埛鐨勯〉闈€傚畠浣跨敤鑷繁鐙壒鐨勬ā鏉胯瑷€锛屽紑鍙戜汉鍛樺彲浠ュ湪妯℃澘涓祵鍏ュ彉閲忋€佹潯浠惰鍙ャ€佸惊鐜瓑鍏冪礌锛屼互瀹炵幇鍔ㄦ€佸唴瀹圭殑鐢熸垚銆?

Velocity 涓?XSS 婕忔礊鍘熺悊

鍙橀噺杈撳嚭鏈繃婊ゆ垨杞箟锛?

鍦?Velocity 妯℃澘涓紝濡傛灉鐩存帴杈撳嚭鐢ㄦ埛鍙帶鐨勫彉閲忥紝鑰屾病鏈夊杩欎簺鍙橀噺杩涜鍚堥€傜殑澶勭悊锛屽氨鍙兘瀵艰嚧 XSS 婕忔礊銆備緥濡傦紝鍦ㄦā鏉夸腑鏈夎繖鏍风殑浠ｇ爜锛?set($userInput = $request.getParameter('input')) <p>$userInput</p>锛岃繖閲?userInput鐩存帴鎺ユ敹鐢ㄦ埛閫氳繃璇锋眰浼犲叆鐨勫弬鏁癷nput锛屽鏋滅敤鎴疯緭鍏ュ寘鍚伓鎰忕殑 JavaScript 浠ｇ爜锛堝<script>alert('xss');</script>锛夛紝褰撻〉闈㈡覆鏌撴椂锛屾祻瑙堝櫒浼氬皢杩欐浠ｇ爜褰撲綔鑴氭湰鎵ц銆?

瀵?HTML 灞炴€х殑涓嶅綋澶勭悊锛?

褰撹緭鍑虹敤鎴锋暟鎹埌 HTML 灞炴€у€间腑鏃讹紝涔熷鏄撳嚭鐜伴棶棰樸€傛瘮濡傦細#set($link = $request.getParameter('link')) <a href="$link">Click here</a>锛屽鏋滄敾鍑昏€呭皢link鍙傛暟璁剧疆涓簀avascript:alert('xss');锛屽綋鐢ㄦ埛鐐瑰嚮閾炬帴鏃讹紝鎭舵剰鑴氭湰灏变細鎵ц銆傛澶栵紝瀵逛簬鍏朵粬 HTML 灞炴€э紝濡俹nclick銆乷nmouseover绛変簨浠跺睘鎬э紝濡傛灉鐢ㄦ埛杈撳叆鐩存帴宓屽叆杩欎簺灞炴€у€间腑鑰屾湭缁忚繃婊わ紝鏀诲嚮鑰呭彲浠ヨ交鏄撳湴娉ㄥ叆鎭舵剰鑴氭湰銆備緥濡傦細#set($action = $request.getParameter('action')) <button onclick="$action">Button</button>锛屾敾鍑昏€呭彲閫氳繃鏋勯€犳伓鎰忕殑action鍊兼潵瑙﹀彂 XSS銆?

妯℃澘涓寘鍚敤鎴峰彲鎺у唴瀹圭殑鍏朵粬鎯呭喌锛?

鍗充娇涓嶆槸绠€鍗曠殑鍙橀噺杈撳嚭锛屽湪鏇村鏉傜殑妯℃澘閫昏緫涓紝濡傛灉鏈夌敤鎴峰彲鎺х殑鍐呭鍙備笌鍒版ā鏉跨敓鎴愯繃绋嬩腑锛屽苟涓旀病鏈夎繘琛屽畨鍏ㄥ鐞嗭紝涔熷彲鑳藉鑷存紡娲炪€傛瘮濡傦紝鍦ㄤ竴涓娇鐢?Velocity 鐢熸垚鐨勯〉闈腑锛屾湁涓€涓垪琛ㄩ」鐨勫唴瀹规槸鐢ㄦ埛杈撳叆鐨勶紝鑰屾ā鏉垮湪鐢熸垚鍒楄〃鏃舵病鏈夊鐢ㄦ埛杈撳叆杩涜杞箟鎴栬繃婊わ紝鏀诲嚮鑰呭氨鍙互鍦ㄨ緭鍏ヤ腑娉ㄥ叆鑴氭湰浠ｇ爜锛屼粠鑰屽奖鍝嶆暣涓〉闈㈢殑瀹夊叏鎬с€?

Chanzi-Separator

淇Velocity鐨刋SS婕忔礊锛屽彲浠ラ噰鍙栦互涓嬪嚑绉嶆柟娉曪細

鏁版嵁缂栫爜锛氬湪Velocity涓紝鍙互浣跨敤${htmlescape}鏉ョ紪鐮丠TML瀹炰綋瀛楃锛屼互闃叉鎭舵剰鑴氭湰娉ㄥ叆銆備緥濡傦細

vm
<script>
    var name = "${htmlescape($username)}";
</script>

涓婅堪浠ｇ爜灏嗕細灏?username鍙橀噺鐨勫€艰繘琛孒TML瀹炰綋缂栫爜锛岀‘淇濅换浣曠壒娈婂瓧绗﹂兘涓嶄細琚В鏋愪负鎭舵剰鑴氭湰銆?

鏍囩/灞炴€х櫧鍚嶅崟锛氬湪鏌愪簺鎯呭喌涓嬶紝鍙兘鍙兂鍏佽鐗瑰畾鐨凥TML鏍囩鎴栧睘鎬у湪妯℃澘涓娇鐢ㄣ€傚彲浠ヤ娇鐢╒elocity鐨?secure涓婁笅鏂囨潵瀹炵幇杩欐牱鐨勭櫧鍚嶅崟杩囨护锛?

vm
$!secure.filter('<h1>Hello World!</h1>', ['h1'])

涓婅堪浠ｇ爜灏嗕細杩囨护鎺夐櫎<h1>鏍囩涔嬪鐨勬墍鏈塇TML鏍囩銆?

閾炬帴URL缂栫爜锛氫负浜嗛槻姝㈡伓鎰忔敞鍏ユ敾鍑伙紝鍙互浣跨敤Velocity鐨?{url}鍑芥暟瀵筓RL杩涜缂栫爜銆?

vm
<a href="${url($linkUrl)}">Link</a>

涓婅堪浠ｇ爜灏嗕細瀵?linkUrl杩涜URL缂栫爜锛岀‘淇濆叾涓笉鍖呭惈鎭舵剰鑴氭湰銆?

杈撳叆楠岃瘉涓庤繃婊わ細鍦ㄥ鐞嗙敤鎴疯緭鍏ユ椂锛屽缁堝鐢ㄦ埛鎻愪緵鐨勬暟鎹繘琛屾楠屽拰杩囨护銆傜‘淇濊緭鍏ョ殑鏁版嵁绗﹀悎棰勬湡锛屽苟杩囨护鎺変换浣曟綔鍦ㄧ殑鎭舵剰鍐呭銆?

涓ユ牸鎺у埗妯℃澘鏉冮檺锛氬浜庡叕寮€鍙闂殑妯℃澘锛岃纭繚鍙湁鎺堟潈鐢ㄦ埛鍙互瀵瑰叾杩涜淇敼銆傞檺鍒跺妯℃澘鐨勮闂潈闄愬彲浠ラ伩鍏嶆伓鎰忚剼鏈殑娉ㄥ叆銆?

鍙婃椂鏇存柊妯℃澘寮曟搸锛氱‘淇濅綘浣跨敤鐨刅elocity鐗堟湰鏄渶鏂扮殑锛屽苟鍙婃椂搴旂敤浠讳綍瀹夊叏琛ヤ竵鎴栨洿鏂般€傝繖鍙互甯姪鎶靛尽宸茬煡婕忔礊鐨勬敾鍑汇€?

浣跨敤Content Security Policy锛圕SP锛夛細CSP鏄竴绉嶅畨鍏ㄧ瓥鐣ワ紝鏈夋晥閰嶇疆鍙互闄愬埗缃戦〉涓彲浠ユ墽琛岀殑鑴氭湰锛岄€氳繃璁剧疆CSP锛屽彲浠ラ樆姝㈡敾鍑昏€呮敞鍏ユ伓鎰忚剼鏈紝鍚屾椂涔熷缓璁厤缃瓹SP鍚庤繘琛屽厖鍒嗘祴璇曪紝閬垮厤鍥犻樆姝簡鍚堟硶璧勬簮鍔犺浇鑰屽鑷存甯镐笟鍔″彈褰卞搷銆?

瀵硅緭鍑鸿繘琛岀紪鐮侊細鍦ㄥ皢鐢ㄦ埛杈撳叆鐨勬暟鎹彃鍏ュ埌HTML椤甸潰涔嬪墠锛屽鍏惰繘琛岀紪鐮侊紝杩欐牱鍙互纭繚鐗规畩瀛楃琚纭鐞嗭紝涓嶄細琚В閲婁负HTML鏍囩鎴朖avaScript浠ｇ爜銆?

閫氳繃涓婅堪鎺柦锛屽彲浠ユ湁鏁堝湴淇鍜岄闃睼elocity涓殑XSS婕忔礊锛屼繚鎶eb搴旂敤鐨勫畨鍏ㄣ€?

Chanzi-Separator
*/

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
  NOT sourceNode.type IN ['Long', 'Integer', 'HttpServletResponse']

MATCH
  (sinkNode:Call)
WHERE
  ('forName' IN sinkNode.selectors AND 'Class' IN sinkNode.receiverTypes) OR
  ('invoke' IN sinkNode.selectors AND 'Method' IN sinkNode.receiverTypes)

MATCH
  p = shortestPath((sourceNode)-[:ARG|REF|CALLS|HAS_CALL*1..16]->(sinkNode))
WHERE
  NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer', 'int', 'long']) AND
  EXISTS {
    MATCH (argNode)-[argRel:ARG]->(sinkNode)
    WHERE
      coalesce(argRel.argIndex, -1) >= 0 AND
      NOT 'Lit' IN labels(argNode) AND
      (sourceNode)-[:ARG|REF|CALLS|HAS_CALL*1..8]->(argNode)
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

涓嶅畨鍏ㄧ殑鍙嶅皠璋冪敤

鍦↗ava涓紝涓嶅畨鍏ㄧ殑鍙嶅皠婕忔礊閫氬父鎸囩殑鏄▼搴忎娇鐢ㄤ笉鍙椾俊浠荤殑杈撳叆鏉ュ姩鎬佸湴鏋勯€犲拰鎵ц浠ｇ爜锛岃繖鍙兘瀵艰嚧鏈巿鏉冪殑浠ｇ爜鎵ц銆佺粫杩囧畨鍏ㄦ帶鍒躲€佹暟鎹硠闇叉垨鍏朵粬瀹夊叏闂銆傝繖绉嶆紡娲炲彂鐢熷湪搴旂敤绋嬪簭浣跨敤鍙嶅皠鏉ュ垱寤哄璞°€佽皟鐢ㄦ柟娉曟垨璁块棶瀛楁鏃讹紝鑰屼笉鍙椾俊浠荤殑鐢ㄦ埛杈撳叆琚敤浜庤繖浜涙搷浣溿€?

涓句緥璇存槑锛?
鍋囪鏈変竴涓狫ava搴旂敤绋嬪簭锛屽畠浣跨敤鍙嶅皠鏉ュ姩鎬佹墽琛岀敤鎴锋寚瀹氱殑鍛戒护銆傚鏋滅敤鎴疯緭鍏ユ病鏈夊緱鍒伴€傚綋鐨勯獙璇佹垨娓呯悊锛屾敾鍑昏€呭彲浠ュ埄鐢ㄨ繖涓€鐐规潵鎵ц鎭舵剰浠ｇ爜銆備緥濡傦細

java
import java.lang.reflect.Method;

public class UnsafeReflection {
    public static void main(String[] args) {
        try {
            Class<?> clazz = Class.forName("java.lang.Runtime");
            Method method = clazz.getMethod("exec", String.class);
            Object runtime = clazz.getDeclaredConstructor().newInstance();
            method.invoke(runtime, "calc.exe"); // 鎵ц璁＄畻鍣ㄧ▼搴?
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
鍦ㄨ繖涓緥瀛愪腑锛屽鏋?java.lang.Runtime"鍜?exec"鏄€氳繃鐢ㄦ埛杈撳叆鑾峰緱鐨勶紝閭ｄ箞鏀诲嚮鑰呭彲浠ユ浛鎹㈣繖浜涘€兼潵鎵ц浠绘剰绯荤粺鍛戒护銆?


Chanzi-Separator

淇鏂规鍖呮嫭锛?

闄愬埗鍙嶅皠鐨勪娇鐢細浠呭湪纭疄闇€瑕佹椂浣跨敤鍙嶅皠锛屽苟涓斿彧鍦ㄥ彈淇′换鐨勪笂涓嬫枃涓娇鐢ㄣ€?

杈撳叆楠岃瘉锛氬鎵€鏈夌敤鎴疯緭鍏ヨ繘琛屼弗鏍肩殑楠岃瘉锛岀‘淇濆畠浠笉鍖呭惈浠讳綍鍙兘瀵艰嚧浠ｇ爜鎵ц鐨勫懡浠ゆ垨琛ㄨ揪寮忋€?

浣跨敤鐧藉悕鍗曪細瀹氫箟涓€涓彈淇′换鐨勭被銆佹柟娉曞拰瀛楁鐨勭櫧鍚嶅崟锛屽苟浠呭厑璁歌繖浜涘畨鍏ㄧ殑鍏冪礌閫氳繃鍙嶅皠琚闂€?

鏈€灏忔潈闄愬師鍒欙細纭繚鎵ц鍙嶅皠鎿嶄綔鐨勪唬鐮佽繍琛屽湪鏈€灏忓繀瑕佹潈闄愪笅锛屼互鍑忓皯娼滃湪鐨勬崯瀹炽€?

寮傚父澶勭悊锛氱‘淇濆弽灏勬搷浣滀腑鐨勫紓甯歌閫傚綋澶勭悊锛屼笉娉勯湶鏁忔劅淇℃伅銆?

瀹夊叏缂栫爜瀹炶返锛氶伒寰畨鍏ㄧ紪鐮佺殑鏈€浣冲疄璺碉紝閬垮厤鍦ㄥ弽灏勪腑浣跨敤澶嶆潅鐨勮〃杈惧紡鎴栦笉鍙椾俊浠荤殑杈撳叆銆?

閫氳繃瀹炴柦杩欎簺鎺柦锛屽彲浠ュ噺灏戝洜涓嶅畨鍏ㄥ弽灏勫鑷寸殑瀹夊叏椋庨櫓銆傚湪瀹為檯寮€鍙戜腑锛屽簲褰撳敖閲忛伩鍏嶄娇鐢ㄤ笉鍙椾俊浠荤殑杈撳叆杩涜鍙嶅皠鎿嶄綔锛屼互闃叉娼滃湪鐨勫畨鍏ㄦ紡娲炪€?

Chanzi-Separator
*/


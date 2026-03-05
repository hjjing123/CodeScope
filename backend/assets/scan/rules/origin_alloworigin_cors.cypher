MATCH
  (sourceNode)
  WHERE
  // String origin = req.getHeader("Origin");
    sourceNode:StringLiteral AND 'getHeader' IN  sourceNode.selectors AND sourceNode.name="\"Origin\""

MATCH
  (sinkNode)
  WHERE
  // resp.setHeader("Access-Control-Allow-Origin", origin);  第二个参数
  'setHeader' IN sinkNode.selectors AND sinkNode.argPosition=1
MATCH
  p = shortestPath((sourceNode)-[*..4]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer'] )

RETURN
  p AS path

/*
Chanzi-Separator

反射型 CORS

1. 完全信任客户端提供的 Origin，并将其设置为Access-Control-Allow-Origin的值
   `Origin` 头是浏览器带过来的，把它的值原封不动地回写到 `Access-Control-Allow-Origin`，则存在 CSRF 风险，可从任意恶意网站发送请求到此服务。

2. 如果设置了允许携带凭证，则风险进一步提高
   `Access-Control-Allow-Credentials: true` 时，`Access-Control-Allow-Origin` 不能为 `*`（规范硬性要求）。
   你这里动态回显任意域名，正好绕过了这一限制，浏览器会**放行带 Cookie / Authorization 头 / 客户端证书**的请求。
   恶意网站在被合法用户访问时，可借助合法用户身份发送恶意请求到此服务，从而造成 CSRF 攻击。

3. 带来的实际危害
   • 偷数据：攻击页通过 `fetch` 访问 `/api/userInfo`，浏览器自动带上受害者的 Session Cookie；响应可被 JS 读取，敏感 JSON 泄露。
   • 改数据：只要接口不额外做 CSRF Token 校验，攻击页就能以受害者身份调 `POST /api/transfer`、`DELETE /api/article/123` 等接口。
   • 绕过 IP/Referer 校验：很多后台只对白名单内网地址放行，攻击者把 `Origin` 写成内网域名就能突破。

------------------------------------------------
二、攻击场景演示（精简版）
------------------------------------------------
攻击者页面 `https://evil.com/poc.html`：

```html
<script>
fetch('https://victim.com/api/balance', {
  method: 'GET',
  credentials: 'include'          // 带上 Cookie
}).then(r => r.json())
  .then(d => alert(d.money));
</script>
```

由于后端返回了
```
Access-Control-Allow-Origin: https://evil.com
Access-Control-Allow-Credentials: true
```
浏览器把响应完全交给 `evil.com` 的脚本，余额泄露。

Chanzi-Separator

修复思路一句话：**“白名单 + 严格比对 + 不反射”**。下面给出三种常用方案，任选其一即可。

1. 静态白名单（最简单、最常用）
```java
Set<String> ALLOW = Set.of("https://app.example.com", "https://spa.example.com");
String origin = req.getHeader("Origin");
if (ALLOW.contains(origin)) {
    resp.setHeader("Access-Control-Allow-Origin", origin);
    resp.setHeader("Access-Control-Allow-Credentials", "true");
} else {
    // 不返回任何 CORS 头，浏览器会按同源策略阻断
}
```

2. 正则白名单（需要通配二级域名时）
```java
Pattern P = Pattern.compile("^https://\\w+\\.example\\.com$");
String origin = req.getHeader("Origin");
if (origin != null && P.matcher(origin).matches()) {
    resp.setHeader("Access-Control-Allow-Origin", origin);
    resp.setHeader("Access-Control-Allow-Credentials", "true");
}
```

3. SameSite + 独立公网域名（彻底根治 CSRF）
   • 把前端 SPA 部署到**独立域名**（如 `https://spa.example.com`），后端 API 使用**不同域名**（如 `https://api.example.com`）。
   • Cookie 设置 `SameSite=Lax`（或 `Strict`），禁止跨站发送。
   • 后端只给 `spa.example.com` 加 CORS 头。
   这样即便攻击者伪造 Origin，也无法携带 Cookie，天然阻断 CSRF。

------------------------------------------------
一句话总结
------------------------------------------------
**不要直接把请求头里的 Origin 回写到响应头。**
永远使用**白名单校验**，并配合 `SameSite Cookie`/`CSRF Token` 做纵深防御。

Chanzi-Separator
*/
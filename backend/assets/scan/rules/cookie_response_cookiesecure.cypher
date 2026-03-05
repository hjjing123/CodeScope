// 先找到设置了 httponly的cookie，后边过滤掉
MATCH
  (filterNode:StringLiteral)
MATCH
  (x)
  WHERE
  (x.selector = 'setHttpOnly')
MATCH
  (filterNode)-[*..30]->(x)
WITH collect(DISTINCT filterNode) AS filterNodes

// 查询设置的敏感cookie，过滤掉设置了 httponly的， 查询语句中强烈不建议用 CONTAINS ，节点多时性能会很差
MATCH
  (sourceNode:StringLiteral)
  WHERE
  (
  (sourceNode.nameLower ENDS WITH '"ticket"') OR
  (sourceNode.nameLower  ENDS WITH  'token') OR
  (sourceNode.nameLower  ENDS WITH  'jwt') OR
  (sourceNode.nameLower  ENDS WITH  'session') OR
  (sourceNode.nameLower  ENDS WITH  'sessionid') OR
  (sourceNode.nameLower  ENDS WITH  'password') OR
  (sourceNode.nameLower  ENDS WITH  'passwd') OR
  (sourceNode.nameLower  ENDS WITH  'pass')
  ) AND
  sourceNode.AllocationClassName = 'Cookie' AND (NOT sourceNode IN filterNodes)
MATCH
  (sinkNode)
  WHERE
  ('addCookie' IN sinkNode.selectors) OR
  ('setCookie' IN sinkNode.selectors)
MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
RETURN
  p AS path


/*
Chanzi-Separator

身份凭据Cookie未设置HttpOnly

HTTP cookies 是服务器发送到用户浏览器并保存在用户本地的小块数据。这些数据在用户浏览网站时可以被服务器读取，用于识别用户、保存会话状态、个人设置等。

HttpOnly 是一个设置在 cookie 中的属性，当它被设置时，意味着这个 cookie 只能被服务器访问，不能被 JavaScript 代码访问。这是一种安全措施，用来减少某些类型的网络攻击，特别是跨站脚本攻击（XSS）。

如果没有设置 HttpOnly 属性，那么这个 cookie 可以被 JavaScript 访问。这意味着在用户的浏览器上运行的任何脚本都有可能读取这个 cookie 的值。

没有 HttpOnly 的 Cookie 的风险：
跨站脚本攻击（XSS）：如果网站存在 XSS 漏洞，攻击者可以注入恶意脚本到页面中，这些脚本可以读取没有 HttpOnly 属性的 cookie，并将其发送到攻击者控制的服务器。这可能导致会话劫持、用户身份冒充和其他安全问题。

信息泄露：即使没有 XSS 漏洞，没有 HttpOnly 属性的 cookie 也可能在用户访问的其他网站上被读取，如果这些网站包含恶意脚本或者与攻击者共享数据。

会话劫持：攻击者可以利用 XSS 漏洞窃取用户的 cookie，然后使用这些 cookie 伪装成用户，执行未授权的操作。

绕过同源策略：攻击者可以使用没有 HttpOnly 属性的 cookie 来绕过同源策略，因为 JavaScript 可以读取并发送这些 cookie 到其他域。

为了减少这些风险，最佳实践是在设置 cookie 时总是包含 HttpOnly 属性。这样可以确保即使网站存在 XSS 漏洞，攻击者也无法通过脚本读取敏感的 cookie 数据。此外，还应该使用 Secure 属性来确保 cookie 仅通过 HTTPS 传输，以及 SameSite 属性来防止跨站请求伪造（CSRF）攻击。

Chanzi-Separator



在Web应用中设置带有`HttpOnly`属性的Cookie，可以防止客户端脚本访问该Cookie，从而减少跨站脚本攻击（XSS）的风险。以下是几种不同编程环境中设置`HttpOnly` Cookie的例子：

### Java Servlet

在Java Servlet中，可以通过`Cookie`对象的`setHttpOnly`方法来设置`HttpOnly`属性。

```java
import javax.servlet.http.Cookie;
import javax.servlet.http.HttpServletResponse;

// ...

HttpServletResponse response = ... // 获取HttpServletResponse对象
Cookie cookie = new Cookie("cookieName", "cookieValue");
cookie.setHttpOnly(true); // 设置HttpOnly属性为true
cookie.setMaxAge(60 * 60 * 24); // 设置Cookie的有效期为一天
response.addCookie(cookie); // 将Cookie添加到响应中
```

### Spring Framework

在Spring框架中，可以通过`ServerHttpResponse`对象设置`HttpOnly`属性。

```java
import org.springframework.http.ResponseCookie;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

// ...

@RestController
public class MyController {

    @GetMapping("/set-cookie")
    public String setCookie(ServerHttpResponse response) {
        ResponseCookie cookie = ResponseCookie.from("cookieName", "cookieValue")
                .httpOnly(true)
                .path("/")
                .build();
        response.addCookie(cookie);
        return "Cookie has been set";
    }
}
```

### PHP

在PHP中，可以通过`setcookie`函数的`httponly`参数来设置`HttpOnly`属性。

```php
<?php
// 设置一个HttpOnly Cookie
setcookie("cookieName", "cookieValue", time() + (86400 * 30), "/", "", false, true);
?>
```

### ASP.NET

在ASP.NET中，可以通过`HttpCookie`对象的`HttpOnly`属性来设置。

```csharp
// 设置一个HttpOnly Cookie
HttpCookie cookie = new HttpCookie("cookieName", "cookieValue");
cookie.HttpOnly = true;
cookie.Expires = DateTime.Now.AddDays(30); // 设置Cookie的有效期为30天
Response.Cookies.Add(cookie);
```

### Node.js (使用 Express)

在Node.js的Express框架中，可以通过`res.cookie`方法的`httpOnly`选项来设置。

```javascript
const express = require('express');
const app = express();

app.get('/set-cookie', (req, res) => {
  res.cookie('cookieName', 'cookieValue', { httpOnly: true, maxAge: 900000 });
  res.send('Cookie has been set');
});

app.listen(3000, () => {
  console.log('Server is running on port 3000');
});
```

在所有这些例子中，我们都设置了`HttpOnly`属性，以确保Cookie不能被客户端脚本访问。这是一个重要的安全措施，可以减少XSS攻击的风险。


Chanzi-Separator
*/

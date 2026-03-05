MATCH
  (sourceNode)
  WHERE
  (
  // jfinal : String keyword=this.getPara("keyword");
    (sourceNode:CallArg AND 'getPara' IN  sourceNode.selectors) OR
    sourceNode.assignRight STARTS WITH 'getParamsMap' OR
    sourceNode.assignRight STARTS WITH 'getParaMap' OR
    // 一些框架自定义注解， 请求入参使用 @HttpParam
    (sourceNode:MethodBinding AND 'HttpParam' IN sourceNode.paramAnnotations)
  ) AND
  NOT sourceNode.type  IN ['Long', 'Integer', 'HttpServletResponse']


MATCH
  (sinkNode)
  WHERE
  'sendRedirect' IN sinkNode.selectors OR
  //    return "redirect:" + url;   // Spring MVC写法 302临时重定向 , 加法表达式左边拼接  redirect:
  sinkNode.addLeft = "\"redirect:\"" OR
    ('setLocation' IN sinkNode.selectors AND 'HttpHeaders' IN  sinkNode.receiverTypes)
MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer','int','long'] )

RETURN
  p AS path

/*
Chanzi-Separator

URL重定向漏洞

Java中的URL重定向漏洞通常发生在Web应用程序在执行重定向操作时未能正确处理用户输入的URL，导致攻击者能够利用该漏洞进行恶意重定向。以下是URL重定向漏洞的基本原理：

    开放重定向：应用程序允许用户输入重定向的目标URL，但没有进行适当的验证和过滤。

    用户输入处理不当：如果应用程序直接使用用户输入构造重定向的URL，攻击者可以提交一个恶意的URL。

    重定向逻辑缺陷：应用程序的重定向逻辑可能存在缺陷，例如，没有限制重定向的目标域或路径。

    攻击者利用：攻击者可以利用这个漏洞将用户重定向到一个恶意网站，这可能用于钓鱼攻击、散布恶意软件或其他攻击。

    信任关系滥用：如果应用程序和其他网站之间存在信任关系，攻击者可以利用重定向漏洞在被信任的网站上执行攻击。

    Web服务器配置：在某些情况下，Web服务器或应用程序服务器的配置不当也可能允许攻击者利用重定向漏洞。

    Cookie和会话劫持：攻击者可能利用URL重定向漏洞来获取用户的Cookie或其他会话信息，尤其是在使用开放重定向到攻击者控制的站点时。

    应用程序逻辑缺陷：应用程序可能在重定向前未清除或验证某些参数，导致攻击者可以传递恶意参数进行攻击。

    防御不足：应用程序可能缺乏足够的输入验证和输出编码机制，未能防止重定向漏洞的发生。


Chanzi-Separator

修复Java中URL重定向漏洞的关键在于确保应用程序不会执行到不受信任的重定向目标。以下是一些具体的修复建议：

    输入验证：对所有用户输入的重定向URL进行严格验证，确保它们符合预期的格式和安全标准。

    白名单：使用白名单方法，只允许重定向到预定义的安全URL列表中的地址。

    限制协议：确保重定向只限于安全的协议，如HTTPS，避免使用不安全的协议如HTTP。

    服务器端检查：在服务器端进行重定向目标的检查，不要仅依赖客户端的验证。

    使用相对路径：如果可能，使用相对路径进行重定向，而不是完整的URL。

    避免使用用户输入：尽量避免直接使用用户输入的参数作为重定向的目标URL。

    参数化重定向：使用参数化的方式进行重定向，例如，在重定向前将目标URL作为参数存储在会话中。

    错误消息安全：确保错误消息不会泄露关于应用程序逻辑或配置的信息。

    使用安全的库：使用成熟的库来处理URL的生成和重定向，避免自己构建可能存在漏洞的逻辑。

    会话管理：确保会话管理是安全的，使用合适的Cookie属性，如HttpOnly和Secure。

    监控和日志记录：实施监控和日志记录机制，以便检测和响应可能的重定向攻击。

    内容安全策略（CSP）：通过实施内容安全策略来限制资源的加载，可以减少某些类型的重定向攻击。

    使用安全的重定向函数：在Java中，使用如HttpServletResponse.sendRedirect()这样的安全函数，并确保正确处理URL。

通过实施这些措施，可以显著降低Java Web应用程序中URL重定向漏洞的风险，并提高应用程序的整体安全性。
Chanzi-Separator
*/
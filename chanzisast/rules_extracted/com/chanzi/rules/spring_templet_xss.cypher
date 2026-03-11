// spring mvc ,使用 模版引擎渲染， 直接返回String 或者 ModelAndView 的情况；排除掉直接返回json的情况
MATCH
  (sourceNode:SpringControllerArg)
  WHERE sourceNode.type <> 'Long' AND sourceNode.type <> 'Integer' AND
  //下边的两行用于 排除掉直接返回json的情况，前后端分离的情况不考虑xss
  'RestController' IN sourceNode.classAnnotations AND
  'ResponseBody' IN sourceNode.methodAnnotations

MATCH (sinkNode)
  WHERE
  ('addAttribute' IN  sinkNode.selectors AND 'Model' IN  sinkNode.receiverTypes) OR
  ('put' IN  sinkNode.selectors AND 'ModelMap' IN  sinkNode.receiverTypes) OR
  ('addObject' IN sinkNode.selectors AND 'ModelAndView' IN sinkNode.receiverTypes)

MATCH
  p = shortestPath((sourceNode)-[*..20]->(sinkNode))
  WHERE
  none(n IN nodes(p)
    WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer','int','long'])
RETURN
  p AS path

/*
Chanzi-Separator

XSS（跨站脚本攻击，Cross-Site Scripting）

xss是一种常见的网络安全漏洞，它允许攻击者将恶意脚本注入到其他用户会浏览的页面中。以下是XSS漏洞的基本原理：

    用户输入处理不当：当Web应用程序未能正确处理或清理用户输入的数据时，就可能发生XSS攻击。

    输出编码不足：应用程序在将用户输入的数据输出到页面时，如果没有进行适当的编码或转义，恶意脚本就可能被执行。

    反射型XSS：当应用程序将用户输入直接输出到当前页面，且没有进行适当的处理时，就可能发生反射型XSS攻击。攻击者可以通过诱使用户点击一个包含恶意脚本的链接来实现攻击。

    存储型XSS：如果应用程序将用户输入存储在数据库中，并且之后在页面上展示这些数据时没有进行适当的处理，就可能发生存储型XSS攻击。这种攻击的恶意脚本会在每次页面加载时执行。

    DOM-based XSS：当应用程序使用JavaScript操作DOM，且操作过程中未能正确处理用户输入时，就可能发生基于DOM的XSS攻击。

    攻击向量：XSS攻击通常利用HTML、JavaScript、CSS或其他客户端脚本语言作为攻击载体。

    攻击目的：攻击者可能利用XSS漏洞盗取用户的Cookie、会话令牌或其他敏感信息，冒充用户执行操作，或者在用户浏览器上执行其他恶意行为。

    受影响的应用：任何允许用户输入并在页面上显示这些输入的Web应用程序都可能受到XSS攻击。

    防御不足：如果应用程序缺乏足够的输入验证、输出编码和安全配置，就更容易受到XSS攻击。


Chanzi-Separator

XSS（跨站脚本攻击）是一种常见的网络安全漏洞，它允许攻击者将恶意脚本注入到网页中，这些脚本在其他用户的浏览器中执行，可能导致敏感信息泄露、会话劫持等安全问题。以下是Java Web应用中常见的XSS漏洞修复建议：

输入过滤和转义：对所有用户输入进行严格的验证和过滤，使用HTML实体编码来转义特殊字符，防止恶意脚本注入。

内容安全策略（CSP）：使用CSP来限制网页可以加载和执行的资源来源，例如脚本、样式表等，从而减少XSS攻击的风险。

框架内置防护：利用Java Web框架（如Spring MVC）内置的XSS防护功能或者配合前端框架 vue 等进行输出转义，例如通过过滤器或拦截器自动对输入数据进行清理。

自定义过滤器：创建自定义的XSS防护过滤器，对请求和响应内容进行处理，以防止XSS攻击。

避免直接内联JavaScript：尽量避免在HTML中直接内联JavaScript代码，可以使用外部文件引入，并通过CSP策略进行控制。

使用安全的API：使用不解释用户输入为代码的DOM操作方法，避免使用如document.write()和innerHTML等可能引发XSS的API。

正则表达式过滤：使用正则表达式对用户输入进行过滤，以防止恶意脚本的注入，通常需要严格限制特殊字符的输入，否则容易被绕过。

Chanzi-Separator
*/
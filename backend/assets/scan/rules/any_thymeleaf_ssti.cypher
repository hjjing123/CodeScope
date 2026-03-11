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
  ('process' IN sinkNode.selectors AND 'ITemplateEngine' IN sinkNode.receivers) OR
  ('process' IN sinkNode.selectors AND 'TemplateEngine' IN sinkNode.receivers) OR
  ('processThrottled' IN sinkNode.selectors AND 'ITemplateEngine' IN sinkNode.receivers) OR
  ('processThrottled' IN sinkNode.selectors AND 'TemplateEngine' IN sinkNode.receivers)

MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer','int','long'] )

RETURN
  p AS path

/*
Chanzi-Separator

Thymeleaf 模版注入

Thymeleaf 是一种现代的服务器端 Java 模板引擎：它允许在 HTML、XML、JavaScript、CSS 等文件中处理模板，使这些文件既能作为模板使用，又能作为静态原型展示。它与 Spring 框架有很好的集成，广泛应用于 Java Web 开发中。

主要特点：

自然模板：其模板语法可以直接在 HTML 文件中使用，不需要特定的模板文件扩展名。例如，可以在 HTML 文件中使用th:text等属性来实现动态内容填充，如<p th:text="${message}">This is a static text</p>，这里${message}是从服务器端传递过来的变量，在模板渲染时会替换掉默认文本。

表达式处理：支持多种表达式类型，包括 OGNL（Object - Graph Navigation Language）、SpringEL 等，用于在模板中处理数据和逻辑。

Thymeleaf 模板注入漏洞原理

表达式执行问题：

Thymeleaf 支持在模板中使用表达式来处理数据。当用户能够控制输入到模板中的内容，并且这些内容被不恰当地作为表达式执行时，就可能导致模板注入漏洞。例如，如果应用程序接受用户输入的模板片段，并且没有对其进行严格的验证和过滤，攻击者可以构造恶意的表达式。

利用 OGNL 或 SpringEL 表达式：

以 OGNL 表达式为例，如果攻击者能够将恶意的 OGNL 表达式注入到模板中，就可能执行任意代码。假设一个应用程序有一个功能是允许用户自定义邮件模板，用户输入的内容会被填充到一个 Thymeleaf 模板中。如果没有安全防护，攻击者可以输入类似${''.getClass().forName('java.lang.Runtime').getRuntime().exec('calc.exe')}（这里以执行 Windows 计算器程序为例，实际攻击场景可能更复杂和恶意）这样的 OGNL 表达式，当模板渲染时，这个表达式可能会被执行，导致安全漏洞。

上下文对象访问：

在 Thymeleaf 中，模板可以访问上下文中的对象。如果攻击者能够通过注入来篡改对这些对象的访问和操作，可能会获取敏感信息或执行恶意操作。例如，攻击者可以尝试通过注入表达式来访问不应该被外部访问的服务器端对象，或者修改这些对象的属性，从而影响应用程序的正常运行和安全性。

Chanzi-Separator

以下是一些修复 Thymeleaf 模板注入漏洞的方法：

1. 输入验证和过滤

白名单验证：

对用户输入到模板中的内容进行严格的白名单验证。确定哪些字符和模式是允许的，如果输入不符合预期的白名单，则拒绝接受。例如，如果模板中只应接受纯文本内容用于显示消息，那么只允许字母、数字、常见标点符号等，拒绝包含特殊表达式语法字符（如${、}等用于 Thymeleaf 表达式的符号）的输入。可以使用正则表达式等技术来实现白名单验证。

对于复杂的输入场景，如用户自定义模板部分，建立更详细的白名单规则。比如，如果允许用户自定义邮件模板中的某些文本区域和有限的变量（如姓名、地址等简单信息），则对这些变量的格式和内容进行严格检查，确保不会被恶意利用来构造注入表达式。

黑名单过滤：

识别和过滤可能用于构造恶意表达式的关键字符和字符串。例如，禁止用户输入包含${、#（Thymeleaf 表达式中的一些关键起始符号）等可能触发表达式执行的字符。然而，黑名单过滤可能存在局限性，因为攻击者可能会找到绕过黑名单的方法，但它可以作为一种辅助的防护手段。

2. 使用安全的模板设计和配置

避免用户输入直接作为模板内容：

尽可能减少用户可控制的输入直接成为 Thymeleaf 模板的一部分。如果有用户输入的内容需要在模板中显示，将其作为纯文本处理，而不是允许它参与表达式计算。例如，使用th:text属性来输出用户输入，这样即使用户输入包含特殊字符，也不会被当作表达式执行。不要使用th:utext（用于输出未转义的文本）等可能存在风险的方式来处理不可信的用户输入，除非有足够的安全防护措施。

限制模板可访问的对象和方法：

在 Thymeleaf 的配置中，明确限制模板能够访问的对象和方法。例如，通过配置上下文对象，只将必要的、安全的对象暴露给模板。不要将敏感的服务器端对象（如数据库连接对象、系统配置对象等）传递到模板的上下文中，防止攻击者通过注入表达式来访问或篡改这些对象。

对于允许模板访问的对象，限制可调用的方法。如果一个对象有一些危险的方法（如执行系统命令的方法），确保这些方法不能被模板中的表达式所调用。

采用前后端分离架构，目前前后端分离架构是更主流的开发方式，数据的渲染交给前端框架，比如 vue、react 等，后端语言不需要进行模板的解析，能够避免 ssti 相关的漏洞。

Chanzi-Separator
*/
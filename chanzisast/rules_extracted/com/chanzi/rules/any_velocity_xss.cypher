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
  ('merge' IN sinkNode.selectors AND 'template' IN sinkNode.receivers) OR
  ('merge' IN sinkNode.selectors AND 'Template' IN sinkNode.receiverTypes)
MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer','int','long'] )

RETURN
  p AS path

/*
Chanzi-Separator

Velocity xss

Velocity 是一种模板引擎：它主要用于将数据与模板相结合生成动态的文本输出，常用于 Web 开发中。例如，在 Java 开发的 Web 应用中，Velocity 可以将后台的数据填充到 HTML 模板中，生成最终呈现给用户的页面。它使用自己独特的模板语言，开发人员可以在模板中嵌入变量、条件语句、循环等元素，以实现动态内容的生成。

Velocity 中 XSS 漏洞原理

变量输出未过滤或转义：

在 Velocity 模板中，如果直接输出用户可控的变量，而没有对这些变量进行合适的处理，就可能导致 XSS 漏洞。例如，在模板中有这样的代码：#set($userInput = $request.getParameter('input')) <p>$userInput</p>，这里$userInput直接接收用户通过请求传入的参数input，如果用户输入包含恶意的 JavaScript 代码（如<script>alert('xss');</script>），当页面渲染时，浏览器会将这段代码当作脚本执行。

对 HTML 属性的不当处理：

当输出用户数据到 HTML 属性值中时，也容易出现问题。比如：#set($link = $request.getParameter('link')) <a href="$link">Click here</a>，如果攻击者将link参数设置为javascript:alert('xss');，当用户点击链接时，恶意脚本就会执行。此外，对于其他 HTML 属性，如onclick、onmouseover等事件属性，如果用户输入直接嵌入这些属性值中而未经过滤，攻击者可以轻易地注入恶意脚本。例如：#set($action = $request.getParameter('action')) <button onclick="$action">Button</button>，攻击者可通过构造恶意的action值来触发 XSS。

模板中包含用户可控内容的其他情况：

即使不是简单的变量输出，在更复杂的模板逻辑中，如果有用户可控的内容参与到模板生成过程中，并且没有进行安全处理，也可能导致漏洞。比如，在一个使用 Velocity 生成的页面中，有一个列表项的内容是用户输入的，而模板在生成列表时没有对用户输入进行转义或过滤，攻击者就可以在输入中注入脚本代码，从而影响整个页面的安全性。

漏洞触发点说明：

在Velocity中，Template类是核心类之一，它代表一个模板文件。Template类的merge方法用于将模板内容与一组指定的属性（通常是键值对形式的数据）合并，生成最终的文本输出。

具体来说，Template类的merge方法的作用如下：

1.数据绑定：merge方法接受一个Context对象作为参数，这个Context对象包含了要绑定到模板中的数据。这些数据可以是简单的变量、复杂的对象，甚至是整个集合。

2.模板渲染：merge方法将Context中的数据与模板文件中定义的标记（如$variable、#foreach、#if等）结合起来，替换模板中的占位符，生成最终的文本输出。

3.输出结果：merge方法将渲染后的文本输出到一个Writer对象中，这个Writer可以是任何实现了java.io.Writer接口的对象，比如StringWriter、FileWriter等。

Chanzi-Separator

修复Velocity的XSS漏洞，可以采取以下几种方法：

数据编码：在Velocity中，可以使用${htmlescape}来编码HTML实体字符，以防止恶意脚本注入。例如：

vm
<script>
    var name = "${htmlescape($username)}";
</script>

上述代码将会将$username变量的值进行HTML实体编码，确保任何特殊字符都不会被解析为恶意脚本。

标签/属性白名单：在某些情况下，可能只想允许特定的HTML标签或属性在模板中使用。可以使用Velocity的$secure上下文来实现这样的白名单过滤：

vm
$!secure.filter('<h1>Hello World!</h1>', ['h1'])

上述代码将会过滤掉除<h1>标签之外的所有HTML标签。

链接URL编码：为了防止恶意注入攻击，可以使用Velocity的${url}函数对URL进行编码。

vm
<a href="${url($linkUrl)}">Link</a>

上述代码将会对$linkUrl进行URL编码，确保其中不包含恶意脚本。

输入验证与过滤：在处理用户输入时，始终对用户提供的数据进行检验和过滤。确保输入的数据符合预期，并过滤掉任何潜在的恶意内容。

严格控制模板权限：对于公开可访问的模板，要确保只有授权用户可以对其进行修改。限制对模板的访问权限可以避免恶意脚本的注入。

及时更新模板引擎：确保你使用的Velocity版本是最新的，并及时应用任何安全补丁或更新。这可以帮助抵御已知漏洞的攻击。

使用Content Security Policy（CSP）：CSP是一种安全策略，有效配置可以限制网页中可以执行的脚本，通过设置CSP，可以阻止攻击者注入恶意脚本，同时也建议配置CSP后进行充分测试，避免因阻止了合法资源加载而导致正常业务受影响。

对输出进行编码：在将用户输入的数据插入到HTML页面之前，对其进行编码，这样可以确保特殊字符被正确处理，不会被解释为HTML标签或JavaScript代码。

通过上述措施，可以有效地修复和预防Velocity中的XSS漏洞，保护Web应用的安全。

Chanzi-Separator
*/
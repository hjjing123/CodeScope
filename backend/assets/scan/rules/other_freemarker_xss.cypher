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
  ('process' IN sinkNode.selectors AND 'template' IN sinkNode.receivers) OR
  ('process' IN sinkNode.selectors AND 'Template' IN sinkNode.receiverTypes)
MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer'] )

RETURN
  p AS path

/*
Chanzi-Separator

FreeMarker XSS漏洞

1. 关于 Freemarker 与 XSS 漏洞

Freemarker：是一款模板引擎，它可以将数据模型和模板文件相结合生成输出文本（如 HTML 页面等）。

XSS（跨站脚本攻击）漏洞：当 Freemarker 在处理用户输入并将其输出到 HTML 页面等场景时，如果没有对输入进行恰当的转义和过滤，攻击者就可能注入恶意脚本（如 JavaScript），这些脚本在受害者的浏览器中执行，从而导致 XSS 漏洞。

2. Freemarker 中 XSS 漏洞产生的情况

变量输出未过滤：在 Freemarker 模板中，如果直接输出用户可控的变量到 HTML 内容中，比如：

html：
<p>${userInput}</p>

如果userInput包含<script>alert('xss');</script>这样的内容，就会在浏览器中执行该脚本，可能窃取用户信息、执行恶意操作等。

HTML 属性输出问题：当输出到 HTML 属性值中时，类似这样：

html：

<div id="myDiv" data-value="${userData}"></div>

如果userData没有经过合适处理，攻击者可以通过构造特殊的值（如" onmouseover="alert('xss')"）来触发 XSS，当用户鼠标移到该div元素上时，恶意脚本就会执行。

Chanzi-Separator

修复Freemarker的XSS漏洞，可以采取以下几种方法：

对用户输入进行HTML转义：这是避免XSS问题的基本方法。在Freemarker模板中，可以通过?html内置函数对变量进行HTML转义。例如，对于用户输入的数据，应该使用${userInput?html}来确保任何HTML标签被正确转义。

使用<#escape>标签：Freemarker提供了<#escape>标签，允许对模板中的变量进行HTML转义。通过在模板中使用<#escape x as x?html>，可以确保在<#escape>和</#escape>之间的所有变量都被转义。

更新配置：在Freemarker的配置中，可以设置recognize_standard_file_extensions为true，并且更改默认文件扩展名为.ftlh，这样可以默认进行HTML转义。

输出编码：当需要安全地显示用户输入的数据时，应该使用输出编码。大多数现代框架都有内置的自动编码和转义功能，确保变量不会被解释为代码而是作为文本显示。

通过上述方法，可以有效地修复和预防Freemarker中的XSS漏洞。

参考：http://freemarker.foofun.cn/dgui_template_valueinsertion.html
Chanzi-Separator
*/
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
  ('eval' IN sinkNode.selectors AND 'JShell' IN sinkNode.receiverTypes)
MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer','int','long'] )

RETURN
  p AS path

/*
Chanzi-Separator

jshell代码执行漏洞

在Java中，jshell本身并不是一个漏洞，而是一个交互式工具，它允许开发者在没有编写完整类文件的情况下执行Java代码片段。然而，如果jshell被不当使用，特别是在处理不受信任的输入时，可能会被利用来执行恶意代码，从而形成所谓的代码注入漏洞。

jshell的代码注入漏洞通常涉及到执行不受信任的代码片段。例如，如果一个Web应用程序允许用户输入被传递给jshell执行，攻击者可能会注入恶意代码来执行系统命令或操作。这种类型的漏洞可以被利用来执行任意代码，导致严重的安全问题。

以下是一个jshell代码注入的示例，这个示例展示了一个简单的JSP页面，它使用jshell执行用户提供的代码片段：

jsp
<%@ page import="jdk.jshell.*" %>
<%!
JShell shell = JShell.builder().build();
%>
<%
String src = request.getParameter("src");
if (src != null) {
    String result = shell.eval(src).toString();
    out.println("Result: " + result);
}
%>

在这个示例中，如果用户通过HTTP请求发送一个名为src的参数，这个参数的值将被传递给jshell的eval方法执行。如果攻击者发送以下请求：

http://example.com/jshell.jsp?src=new%20String(Runtime.getRuntime().exec(%22cmd%20/c%20dir%22).getInputStream().readAllBytes())

这将导致jshell执行Windows命令dir，列出当前目录下的文件和文件夹。这是一个非常简化的例子，实际攻击中可能会使用更复杂的命令来获取敏感信息或执行恶意操作。

Chanzi-Separator

修复方案包括：

输入验证：对所有用户输入的数据进行严格的验证，确保输入符合预期的格式和内容。例如，对于一个只需要接收数字的输入字段，要验证输入是否确实是数字。

数据过滤：过滤掉可能导致代码注入的特殊字符和关键字。例如，过滤掉单引号、双引号、分号、括号等特殊字符。

使用参数化查询：尽量避免将用户的输入传入 jshell 的 eval 方法,而且采用其他更安全的方式实现业务逻辑.

通过实施这些防范措施，可以有效地降低jshell注入攻击的风险，保护应用程序和系统的安全。

Chanzi-Separator
*/
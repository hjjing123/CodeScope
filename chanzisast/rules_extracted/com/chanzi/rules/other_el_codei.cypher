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
  ('createValueExpression' IN sinkNode.selectors AND 'ExpressionFactory' IN sinkNode.receiverTypes)
MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer','int','long'] )

RETURN
  p AS path

/*
Chanzi-Separator

EL注入漏洞（Expression Language Injection）

EL注入是一种常见的安全漏洞，它发生在应用程序错误地处理用户输入，并将这些输入作为EL表达式的一部分进行解析和执行时。攻击者可以利用这个漏洞执行恶意代码，获取敏感信息，或者破坏应用程序的正常运行。

EL注入漏洞的原理：

EL（Expression Language）是Java EE标准的一部分，它用于在JSP页面中简化数据的访问和表达式的计算。EL表达式通常在JSP页面中使用${}进行标记。如果应用程序将用户输入直接嵌入到EL表达式中，攻击者就可能通过精心构造的输入，注入恶意的EL表达式，从而执行非法操作。
攻击示例：

假设有一个JSP页面，其中使用了EL表达式来显示用户输入的消息：

jsp

<%@ taglib uri="http://www.springframework.org/tags" prefix="spring"%>
<spring:message text="${param.message}"></spring:message>

如果用户输入的是：

<spring:message text="${''.getClass().forName('java.lang.Runtime').getMethod('getRuntime').invoke(null).exec('calc')}">

这将导致JSP页面执行calc命令（计算器程序），这就是一个典型的EL注入攻击。

Chanzi-Separator

EL注入漏洞的修复方案通常包括以下几个方面：

输入验证：对所有用户输入进行严格的验证和过滤，确保不包含EL表达式的起始和结束符号（如$和{}）。这可以防止恶意输入被解析为EL表达式。

使用白名单：对于用户输入，使用白名单来限制允许的字符或模式，从而减少潜在的注入风险。

禁用EL表达式：在不需要使用EL表达式的地方，通过设置isELIgnored="true"来禁用EL表达式的解析，可以在web.xml中进行全局配置，或者在JSP页面中进行局部禁用。

使用安全的API：使用安全的API来处理用户输入，避免直接将用户输入嵌入到EL表达式中。

避免输入表达式：通常不建议直接让用户输入表达式，表达式强大而灵活很容易成为攻击的对象，如果有必要让用户输入表达式，务必做好前置的用户权限校验和输入校验。

Chanzi-Separator
*/
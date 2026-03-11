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
  ('getValue' IN sinkNode.selectors AND 'Ognl' IN sinkNode.receivers)
MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer','int','long'] )

RETURN
  p AS path

/*
Chanzi-Separator

OGNL 表达式注入

OGNL（Object-Graph Navigation Language）是一种用于访问和操作对象图的表达式语言，它在Java中被广泛应用，尤其是在Apache Struts等框架中。OGNL表达式注入漏洞通常发生在应用程序使用OGNL解析用户输入时，如果没有对表达式进行适当的限制或过滤，攻击者可以构造恶意的OGNL表达式来执行任意代码。

漏洞原理：
OGNL注入漏洞的原理是攻击者通过构造恶意的OGNL表达式，可以绕过应用程序的安全限制，执行不应该被执行的操作。例如，攻击者可以利用OGNL的反射功能来执行系统命令或访问敏感数据。
Chanzi-Separator

升级依赖：确保使用的OGNL库是最新版本的，以便利用最新的安全修复。

输入验证：对所有进入OGNL表达式解析器的输入进行严格的验证和过滤，确保它们不包含恶意代码。

使用白名单：定义一个安全的操作和对象的白名单，只允许执行白名单内的表达式。

禁用不必需的功能：如果应用程序不需要执行复杂的OGNL表达式，可以考虑禁用或限制这些功能。

沙箱环境：在沙箱环境中执行OGNL表达式，以限制表达式可以执行的操作。
错误处理与日志记录：合理处理异常和错误，避免泄露敏感信息。同时，记录关键的安全事件和异常，以便于后续分析和审计。
避免输入表达式：通常不建议直接让用户输入表达式，表达式强大而灵活很容易成为攻击的对象，如果有必要让用户输入表达式，务必做好前置的用户权限校验和输入校验。

Chanzi-Separator
*/
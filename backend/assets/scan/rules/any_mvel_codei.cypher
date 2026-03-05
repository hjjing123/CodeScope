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
  ('eval' IN sinkNode.selectors AND 'MVEL' IN sinkNode.receiverTypes)
MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer','int','long'] )

RETURN
  p AS path

/*
Chanzi-Separator

mven表达式注入

MVEL（MVFLEX Expression Language）是一种动态类型化的表达式语言，它的语法受到Java的启发，但设计得更为高效。MVEL表达式可以执行属性表达式、布尔表达式、方法调用、变量赋值和函数定义等操作。MVEL注入漏洞通常发生在应用程序使用MVEL表达式处理用户输入时，如果没有对表达式进行适当的限制或过滤，攻击者可以构造恶意的表达式来执行任意代码。

漏洞原理：MVEL注入漏洞的原理在于，攻击者通过构造恶意的MVEL表达式，可以绕过应用程序的安全限制，执行不应该被执行的代码。例如，攻击者可以利用MVEL的反射功能或其他高级功能来执行系统命令或访问敏感数据。
Chanzi-Separator

升级依赖：确保使用的MVEL库是最新版本的，以便利用最新的安全修复。
输入验证：对所有进入MVEL表达式解析器的输入进行严格的验证和过滤，确保它们不包含恶意代码。
使用白名单：定义一个安全的操作和对象的白名单，只允许执行白名单内的表达式。
禁用不必需的功能：如果应用程序不需要执行复杂的MVEL表达式，可以考虑禁用或限制这些功能。
沙箱环境：在沙箱环境中执行MVEL表达式，以限制表达式可以执行的操作。
最小化权限：确保Java应用程序运行在具有最低必要权限的用户或账户下，减少潜在的攻击面。
错误处理与日志记录：合理处理异常和错误，避免泄露敏感信息。同时，记录关键的安全事件和异常，以便于后续分析和审计。
避免输入表达式：通常不建议直接让用户输入表达式，如果有必要让用户输入表达式，务必做好前置的用户权限校验和输入校验。

Chanzi-Separator
*/
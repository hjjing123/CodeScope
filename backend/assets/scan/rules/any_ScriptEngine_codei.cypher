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
  ('eval' IN sinkNode.selectors AND 'ScriptEngine' IN sinkNode.receiverTypes) OR
  ('getProgram' IN sinkNode.selectors AND 'ScriptEngineFactory' IN sinkNode.receiverTypes) OR
  ('getMethodCallSyntax' IN sinkNode.selectors AND 'ScriptEngineFactory' IN sinkNode.receiverTypes) OR
  ('evaluateString' IN sinkNode.selectors AND 'Context' IN sinkNode.receiverTypes)

MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer','int','long'] )

RETURN
  p AS path

/*
Chanzi-Separator

ScriptEngine注入漏洞

ScriptEngine注入漏洞主要发生在Java应用程序中，当应用程序使用javax.script.ScriptEngineManager来执行动态脚本时，如果没有对用户输入进行适当的限制或过滤，攻击者可以构造恶意的脚本代码，从而执行任意Java代码。

漏洞原理：

攻击者通过控制传递给ScriptEngine.eval()方法的参数，注入恶意代码。例如，攻击者可以注入类似java.lang.Runtime.getRuntime().exec("calc")的代码来执行系统命令。
Chanzi-Separator

输入验证：对所有传递给ScriptEngine的输入进行严格的验证，确保它们不包含恶意代码。可以使用黑名单或白名单的方式来控制允许执行的代码类型。

使用沙箱环境：在沙箱环境中执行脚本，以限制脚本可以执行的操作。沙箱可以是底层的Java安全沙箱，或者是专门的JavaScript沙箱。

自定义SecurityManager：通过自定义SecurityManager来限制脚本可以执行的操作，例如重写checkExec()方法来禁止脚本执行系统命令。

禁用eval函数：如果可能，避免使用eval函数，因为它可以执行任意代码。

限制权限：确保脚本引擎运行在有限的权限下，例如限制网络访问、文件系统访问等。

使用成熟的框架：使用成熟的框架和库，它们通常提供了更好的安全措施。

避免输入脚本：通常不建议直接让用户输入脚本，如果有必要让用户输入脚本，务必做好前置的用户权限校验和输入校验。

Chanzi-Separator
*/
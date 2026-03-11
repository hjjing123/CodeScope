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
  ('parseExpression' IN sinkNode.selectors AND 'SpelExpressionParser' IN sinkNode.receiverTypes) OR
  ('parseExpression' IN sinkNode.selectors AND 'ExpressionParser' IN sinkNode.receiverTypes) OR
  ('parseExpression' IN sinkNode.selectors AND 'TemplateAwareExpressionParser' IN sinkNode.receiverTypes)
MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer','int','long'] )

RETURN
  p AS path

/*
Chanzi-Separator

SPEL注入

Spring Expression Language（简称SpEL）是一种功能强大的表达式语言，用于在运行时查询和操作对象图。它支持在Spring框架中进行复杂的表达式计算，包括方法调用、属性访问、关系运算等。然而，SpEL的强大功能也可能导致安全问题，特别是当用户输入未被正确过滤时，就可能发生SpEL注入漏洞。

SpEL注入漏洞的原理：

SpEL注入漏洞通常发生在应用程序使用SpEL解析用户输入的情况下。如果用户能够控制传递给SpEL解析器的表达式，并且这些表达式没有得到适当的限制或过滤，攻击者可以构造恶意的SpEL表达式来执行任意代码。例如，攻击者可以通过SpEL表达式调用java.lang.Runtime类的exec方法来执行系统命令。


Chanzi-Separator

SpEL注入漏洞的修复方案主要集中在限制SpEL表达式的执行环境，以及对用户输入进行严格的验证和过滤。以下是一些具体的修复措施：

升级Spring版本：确保你使用的Spring框架是最新版本的，以便利用最新的安全修复。例如，Spring Boot 1.3.1及以上版本修复了旧版本中的SpEL注入问题。

使用SimpleEvaluationContext：在不指定EvaluationContext的情况下，默认采用StandardEvaluationContext，它包含了SpEL的所有功能。为了安全起见，可以使用SimpleEvaluationContext，它只支持SpEL语法的一个子集，不包括Java类型引用、构造函数和bean引用。

输入验证：对所有传递给SpEL解析器的输入进行严格的验证和过滤，确保它们不包含恶意代码。

使用白名单：定义一个安全的操作和对象的白名单，只允许执行白名单内的表达式。

使用安全的库：如果使用第三方库，确保它们是最新的并且没有已知的安全问题。

自定义SecurityManager：通过自定义SecurityManager来限制SpEL表达式可以执行的操作。

避免输入表达式：通常不建议直接让用户输入表达式，表达式强大而灵活很容易成为攻击的对象，如果有必要让用户输入表达式，务必做好前置的用户权限校验和输入校验。

Chanzi-Separator
*/
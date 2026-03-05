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
  ('execute' IN sinkNode.selectors AND 'ExpressRunner' IN sinkNode.receiverTypes)
MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer'] )

RETURN
  p AS path

/*
Chanzi-Separator

QLExpress表达式注入

QLExpress 是一个 Java 表达式引擎，它允许用户执行类似脚本的表达式。如果不正确地限制用户输入，QLExpress 可以被用来执行任意代码，这就是所谓的任意代码执行（Arbitrary Code Execution, ACE）漏洞。

任意代码执行漏洞的原理通常包括以下几个方面：

    动态执行用户输入：
    如果应用程序接收用户输入并将其作为代码执行，而没有适当的限制或过滤，攻击者就可以利用这一点执行任意代码。

    缺乏安全措施：
    应用程序没有实施足够的安全措施来限制或监控执行的代码。这可能包括白名单（只允许特定的安全操作）和黑名单（禁止不安全的操作）。

    表达式引擎的功能滥用：
    攻击者可能会发现表达式引擎的某些功能可以被滥用来执行恶意代码。例如，如果表达式引擎允许调用 Java 反射或其他动态代码执行技术，攻击者可能会利用这些功能。

    服务端渲染不当：
    如果服务端渲染用户输入时没有进行适当的编码或转义，攻击者可能会注入恶意脚本，导致其他用户或服务端执行恶意代码。

    不安全的反序列化：
    如果表达式引擎允许执行反序列化操作，攻击者可能会利用这一点来执行恶意代码。

在您提供的代码示例中，ExpressRunner 类的 execute 方法被用来执行用户通过 HTTP 请求发送的表达式。如果没有适当的安全措施，攻击者可以发送恶意表达式，导致服务器执行攻击者控制的代码。

例如，攻击者可能会尝试执行以下操作：

    加载和执行恶意类。
    访问和修改服务器上的敏感文件。
    执行系统命令。
    利用 Java 反射或其他技术调用不安全的方法。


Chanzi-Separator

修复 QLExpress 任意代码执行漏洞的关键是限制表达式引擎可以执行的操作。以下是一些推荐的修复措施：

    限制表达式功能：
        仅允许执行必要的操作，例如简单的数学计算和字符串处理。
        禁止执行任何形式的反射、动态类加载或系统命令执行。

    输入验证：
        对用户输入进行严格的验证，确保它们不包含恶意代码。
        使用白名单验证，只允许已知安全的函数和操作。

    安全配置：
        审查和更新 QLExpress 的安全配置，确保它符合安全最佳实践。
        使用 QLExpressRunStrategy 来限制可以执行的方法和类。

    更新和维护：
        定期更新 QLExpress 库，以修复已知的安全漏洞。
        跟踪 QLExpress 的安全公告和更新。

Chanzi-Separator
*/
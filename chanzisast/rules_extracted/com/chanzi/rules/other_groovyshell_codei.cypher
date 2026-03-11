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
  ('evaluate' IN sinkNode.selectors AND 'GroovyShell' IN sinkNode.receiverTypes) OR
  ('parseClass' IN sinkNode.selectors AND 'GroovyClassLoader' IN sinkNode.receiverTypes) OR
  ('parse' IN sinkNode.selectors AND 'GroovyShell' IN sinkNode.receiverTypes) OR
  ('run' IN sinkNode.selectors AND 'GroovyShell' IN sinkNode.receiverTypes) OR
  ('createTemplate' IN sinkNode.selectors AND 'TemplateEngine' IN sinkNode.receiverTypes)
MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer'] )

RETURN
  p AS path

/*
Chanzi-Separator

GroovyShell代码执行

GroovyShell 是 Apache Groovy 编程语言的一部分，它是一个允许你动态执行 Groovy 代码的组件。Groovy 是一种动态语言，与 Java 兼容，它可以被编译成 Java 字节码并运行在任何 Java 虚拟机上。
GroovyShell 代码注入漏洞的原理与许多其他代码注入漏洞类似，都涉及到了用户可控输入被未经过滤、未经验证地执行。以下是代码注入漏洞的一般原理：

    用户输入控制：
    如果应用程序接受用户输入，并将其作为代码片段传递给 GroovyShell 执行，而没有适当的限制或过滤，攻击者就可以构造恶意输入。

    动态执行：
    GroovyShell 动态执行传递给它的代码。如果攻击者能够控制这部分代码，他们就可以执行任意 Groovy 代码。

    缺乏安全措施：
    应用程序没有实施足够的安全措施来限制或监控执行的代码。这可能包括白名单（只允许特定的安全操作）和黑名单（禁止不安全的操作）。

    攻击者利用：
    攻击者可能会利用这些漏洞来执行恶意代码，例如访问或修改服务器上的文件、执行系统命令、访问数据库或其他敏感操作。

    安全漏洞：
    如果 GroovyShell 执行了恶意代码，可能会导致远程代码执行（RCE）、权限提升、数据泄露或其他安全问题。


Chanzi-Separator

修复 GroovyShell 代码注入漏洞的关键在于限制执行环境，确保用户输入不能被解释为恶意代码。以下是一些修复措施：

    输入验证：
        对所有用户输入进行严格的验证，确保它们不包含任何潜在的恶意代码。
        可以使用正则表达式、安全列表或沙箱环境来验证输入。

    使用受限的GroovyShell：
        创建一个受限的 GroovyShell 实例，限制可以执行的方法和类。
        可以通过 GroovyShell 的构造函数传入一个 Binding 对象，该对象可以限制对变量和方法的访问。

    禁用脚本的某些功能：
        禁用脚本执行系统命令的能力，例如通过设置安全策略来禁止 Runtime.exec 方法的调用。

    使用Groovy沙箱：
        使用 Groovy 的沙箱实现，如 SandboxExtension，来限制脚本的执行环境。

    代码白名单：
        仅允许执行预定义的、安全的代码片段，不允许执行任何用户输入的代码。

避免输入表达式：
通常不建议直接让用户输入表达式，表达式强大而灵活很容易成为攻击的对象，如果有必要让用户输入表达式，务必做好前置的用户权限校验和输入校验。

Chanzi-Separator
*/
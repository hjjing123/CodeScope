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
  ('forName' IN sinkNode.selectors AND 'Class' IN sinkNode.receiverTypes) OR
  ('invoke' IN sinkNode.selectors AND 'Method' IN sinkNode.receiverTypes)
MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer'] )

RETURN
  p AS path

/*
Chanzi-Separator

不安全的反射调用

在Java中，不安全的反射漏洞通常指的是程序使用不受信任的输入来动态地构造和执行代码，这可能导致未授权的代码执行、绕过安全控制、数据泄露或其他安全问题。这种漏洞发生在应用程序使用反射来创建对象、调用方法或访问字段时，而不受信任的用户输入被用于这些操作。

举例说明：
假设有一个Java应用程序，它使用反射来动态执行用户指定的命令。如果用户输入没有得到适当的验证或清理，攻击者可以利用这一点来执行恶意代码。例如：

java
import java.lang.reflect.Method;

public class UnsafeReflection {
    public static void main(String[] args) {
        try {
            Class<?> clazz = Class.forName("java.lang.Runtime");
            Method method = clazz.getMethod("exec", String.class);
            Object runtime = clazz.getDeclaredConstructor().newInstance();
            method.invoke(runtime, "calc.exe"); // 执行计算器程序
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
在这个例子中，如果"java.lang.Runtime"和"exec"是通过用户输入获得的，那么攻击者可以替换这些值来执行任意系统命令。


Chanzi-Separator

修复方案包括：

限制反射的使用：仅在确实需要时使用反射，并且只在受信任的上下文中使用。

输入验证：对所有用户输入进行严格的验证，确保它们不包含任何可能导致代码执行的命令或表达式。

使用白名单：定义一个受信任的类、方法和字段的白名单，并仅允许这些安全的元素通过反射被访问。

最小权限原则：确保执行反射操作的代码运行在最小必要权限下，以减少潜在的损害。

异常处理：确保反射操作中的异常被适当处理，不泄露敏感信息。

安全编码实践：遵循安全编码的最佳实践，避免在反射中使用复杂的表达式或不受信任的输入。

通过实施这些措施，可以减少因不安全反射导致的安全风险。在实际开发中，应当尽量避免使用不受信任的输入进行反射操作，以防止潜在的安全漏洞。

Chanzi-Separator
*/
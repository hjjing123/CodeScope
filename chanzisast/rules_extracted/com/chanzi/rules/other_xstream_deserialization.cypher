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
  ('fromXML' IN sinkNode.selectors AND 'XStream' IN sinkNode.receiverTypes)
MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer'] )

RETURN
  p AS path

/*
Chanzi-Separator

XStream反序列化漏洞

XStream 是一个 Java 库，用于将对象序列化成 XML 格式以及将 XML 反序列化成 Java 对象。XStream 反序列化漏洞的工作原理基于 Java 的对象反序列化机制，该机制允许从一系列字节（如 XML 数据）重建 Java 对象。如果不正确地配置，XStream 可以被用来执行任意代码。
工作原理：

    反序列化过程：
        当 XStream 接收到一个 XML 字符串并尝试将其转换回 Java 对象时，它会根据 XML 中的类名信息创建相应的对象实例。

    利用 Java 反射：
        XStream 在反序列化过程中使用 Java 反射 API 来创建对象和调用方法。如果 XML 数据包含对特定类的引用，XStream 会尝试实例化这些类。

    构造器注入：
        如果 XML 数据包含对构造器的调用，XStream 会使用这些构造器来创建对象。攻击者可以构造恶意的 XML，使其在反序列化时调用恶意构造器。

    方法调用：
        XStream 允许在 XML 中指定方法调用，如 field[methodName]。攻击者可以利用这一点来执行对象上的任意方法。

    对象引用：
        XStream 支持对象引用，这意味着它可以处理复杂的对象图。如果 XML 数据包含对已存在对象的引用，XStream 会尝试解析这些引用。

    利用已知漏洞：
        如果 XML 数据包含对已知漏洞类的引用，如 CommonsBeanutils1，XStream 反序列化时可能会触发这些漏洞。

Chanzi-Separator

修复 XStream 反序列化漏洞需要采取一系列措施来确保应用程序不会执行恶意代码。以下是一些推荐的修复方案：

    限制允许的类型：
        使用 XStream 的安全模式，仅允许已知安全的类进行反序列化。可以通过 allowTypes() 方法设置白名单。

    java

XStream xstream = new XStream();
xstream.allowTypesByRegExp(new String[] {"java.lang.", "java.util."});

使用黑名单：

    如果某些类是已知不安全的，可以使用 denyTypes() 方法设置黑名单，禁止这些类的反序列化。

java

    xstream.denyTypes(new String[] {"java.lang.Runtime", "java.lang.ProcessBuilder"});

    禁用不安全的方法：
        使用 xstream.omitField() 方法来排除不安全或敏感的字段。

    使用 XStream 的最新版本：
        确保你使用的 XStream 库是最新版本，以利用最新的安全修复。

    输入验证：
        对所有用户输入进行严格的验证，确保它们不包含潜在的恶意代码。

    使用安全的解析器：
        如果可能，使用 XStream 的安全解析器，或者考虑使用其他更安全的序列化库。

    避免使用 XStream：
        如果可能，考虑使用其他更安全的序列化/反序列化库，或者避免在应用程序中使用 XStream。

通过实施这些措施，可以显著降低 XStream 反序列化漏洞的风险，并保护你的应用程序免受攻击。

Chanzi-Separator
*/
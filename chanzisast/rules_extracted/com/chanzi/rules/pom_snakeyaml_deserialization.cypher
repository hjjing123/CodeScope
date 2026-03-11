// pom 的版本号可能是放在 properties标签里的， dependence标签里使用${xxx.version} 的方式引入
// 所以 sink点的version 是 ${xxx.version} ，而 realVersion才是真实的版本号
MATCH
  (sinkNode:PomDependency|GradleDependency)
  WHERE
  sinkNode.groupId = 'org.yaml' AND   sinkNode.artifactId = 'snakeyaml' AND sinkNode.realVersion STARTS WITH '1.'
RETURN
  sinkNode AS path

/*
Chanzi-Separator

SnakeYAML反序列化漏洞

SnakeYAML 是一个流行的 Java 库，用于解析和生成 YAML 数据。它提供了一个简单的 API 来处理 YAML 文件和字符串。然而，SnakeYAML 也存在一个广为人知的安全问题，即反序列化漏洞。
漏洞原理：

反序列化漏洞发生在应用程序加载不安全或恶意制作的序列化数据时，攻击者可以利用这些漏洞执行任意代码。在 SnakeYAML 的情况下，漏洞的原理通常包括以下几个方面：

    任意对象反序列化：
        SnakeYAML 解析器在加载 YAML 数据时，可能会反序列化不安全的对象，如果攻击者能够控制 YAML 内容，他们可以构造恶意的 YAML 数据，以创建恶意对象。

    利用 Java 反射：
        攻击者可以利用 Java 的反射 API 来创建和操作对象，包括那些具有 readObject 方法的对象，这些对象在反序列化时可能会执行恶意代码。

    利用 Java 序列化机制：
        Java 序列化机制允许对象在序列化和反序列化过程中执行代码。攻击者可以创建包含恶意代码的自定义序列化对象。

    利用 YAML 构造器：
        YAML 构造器（Constructor）可以被用来创建任何对象，包括那些具有副作用的对象，如创建文件、执行系统命令等。

Chanzi-Separator

SnakeYAML 反序列化漏洞的修复需要采取一系列措施来确保应用程序不会执行恶意代码。以下是一些推荐的修复方案：

    更新 SnakeYAML：
        确保你使用的 SnakeYAML 库是最新版本，因为新版本可能已经修复了已知的漏洞。

    使用安全的构造器：
        SnakeYAML 允许你使用 SafeConstructor，它是一个安全的构造器，不会实例化除了基本类型之外的任何对象。这可以防止反序列化攻击。

    java

    YAML yaml = new YAML(new SafeConstructor());

    限制允许的类：
        如果你使用的 SnakeYAML 版本支持，可以配置一个自定义的构造器来限制允许反序列化的类。

    禁用对象引用：
        在 YAML 中，对象引用可能会导致重复的对象实例化。确保你的应用程序配置了不允许对象引用的解析器。

    使用白名单：
        实现一个白名单，只允许已知安全的类和对象被反序列化。

    避免加载外部资源：
        如果 YAML 数据包含对外部资源的引用（如远程 URL 或文件系统路径），确保这些引用被适当地过滤或验证。

    使用独立的解析器：
        对于不需要反序列化成 Java 对象的 YAML 数据，使用独立的解析器来避免执行任何 Java 代码。

    输入验证：
        对所有用户输入进行严格的验证，确保它们不包含潜在的恶意代码。

通过实施这些措施，可以显著降低 SnakeYAML 反序列化漏洞的风险，并保护你的应用程序免受攻击。

Chanzi-Separator
*/
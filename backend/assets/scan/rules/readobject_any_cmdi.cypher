MATCH
  (sourceNode:Argument)
  WHERE
  sourceNode.type = 'ObjectInputStream' AND
  sourceNode.method = 'readObject'

MATCH
  (sinkNode)
  WHERE
  // 命令执行
  ('exec' IN  sinkNode.selectors AND 'Runtime' IN  sinkNode.receiverTypes) OR
  sinkNode.AllocationClassName = 'ProcessBuilder' OR
  ('command' IN sinkNode.selectors AND 'ProcessBuilder' IN sinkNode.receiverTypes) OR
  //  反射调用
  ('forName' IN sinkNode.selectors AND 'Class' IN sinkNode.receiverTypes) OR
  ('invoke' IN sinkNode.selectors AND 'Method' IN sinkNode.receiverTypes)

MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
  WHERE none(n IN nodes(p)
    WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer', 'int', 'long'])
RETURN
  p AS path

/*
Chanzi-Separator

不安全的readobject实现

在 Java 中，readObject 方法是 ObjectInputStream 类中的一个核心方法，用于将字节序列反序列化为对象。它是 Java 序列化机制的一部分，当一个实现了 Serializable 接口的对象被反序列化时，会调用 readObject 方法。

readObject 的作用

反序列化对象：readObject 方法从输入流中读取字节序列，并将其恢复为对象。它会根据序列化时的类信息，重新构造对象的实例。

自定义反序列化逻辑：如果类中定义了 private void readObject(ObjectInputStream in) 方法，Java 会在反序列化时调用这个自定义方法，而不是默认的反序列化逻辑。这允许开发者在反序列化过程中执行额外的逻辑，例如验证数据、初始化非序列化的字段（transient 字段）。

不安全的反序列化实现，是在通过重写readObject来自定义反序列化时，没有充分验证的情况下对不可信数据进行危险操作，比如作为命令执行参数。这种行为可能导致以下安全风险：

远程代码执行 (RCE)：攻击者可以通过构造恶意的序列化数据，在反序列化过程中执行任意代码。

拒绝服务 (DoS)：恶意数据可能导致应用程序崩溃或资源耗尽。

数据泄露：攻击者可以通过反序列化漏洞访问敏感数据。

权限提升：攻击者可能通过漏洞提升其在系统中的权限。

Chanzi-Separator

为了避免不安全的反序列化问题，可以采取以下措施：

限制反序列化的类：通过重写 ObjectInputStream 的 resolveClass 方法，限制可以被反序列化的类。这可以通过白名单或黑名单机制实现。

java
public class SafeObjectInputStream extends ObjectInputStream {
    public SafeObjectInputStream(InputStream in) throws IOException {
        super(in);
    }

    @Override
    protected Class<?> resolveClass(ObjectStreamClass desc) throws IOException, ClassNotFoundException {
        if (!desc.getName().equals("AllowedClassName")) {
            throw new InvalidClassException("Unauthorized deserialization attempt");
        }
        return super.resolveClass(desc);
    }
}

避免反序列化不可信数据：永远不要反序列化来自不可信源的数据。如果必须处理不可信数据，确保对数据进行严格的验证。

使用安全的序列化格式：考虑使用更安全的序列化格式（如 JSON 或 XML）代替 Java 原生序列化。

更新和修补：确保使用最新版本的 Java 和相关库，以避免已知的反序列化漏洞。

通过这些措施，可以有效降低不安全反序列化带来的风险，保护应用程序免受攻击。

Chanzi-Separator
*/
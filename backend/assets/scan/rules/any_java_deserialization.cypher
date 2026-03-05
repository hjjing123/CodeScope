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
  ( sinkNode.selector='readObject'  AND  sinkNode.type='ObjectInputStream')
MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer','int','long'] )

RETURN
  p AS path

/*
Chanzi-Separator

Java反序列化漏洞

漏洞的基本原理涉及到Java对象序列化机制的安全性问题。序列化是Java中一种将对象状态转换为可存储或可传输的格式的过程，而反序列化则是这一过程的逆过程。以下是Java反序列化漏洞的基本原理：

序列化机制：Java提供了序列化机制，允许开发人员将对象状态保存到文件、数据库或通过网络传输。要使一个对象可序列化，它必须实现Serializable接口。

反序列化过程：反序列化是将一个对象从其序列化形式恢复为一个活的对象实例的过程。这个过程由Java的反序列化机制自动完成。

漏洞产生：当应用程序接受来自不可信来源的序列化数据，并尝试反序列化时，如果数据被恶意构造，就可能触发漏洞。

恶意类加载：攻击者可以构造一个包含恶意类的序列化对象，当这个对象被反序列化时，恶意类将被加载并执行。

利用链：攻击者可以利用Java类加载机制中的漏洞（如Commons Collections漏洞），通过反序列化触发一系列操作，最终实现代码执行。

信任关系滥用：如果应用程序存在对外部数据的信任关系，攻击者可以利用这一点，通过构造特殊的序列化数据来执行攻击。

安全配置不当：如果Java安全配置不当，例如允许危险的类被加载和执行，就可能增加反序列化漏洞的风险。

防御不足：应用程序缺乏足够的安全措施来验证和清理序列化数据，未能防止恶意序列化数据的反序列化。


Chanzi-Separator

Java反序列化漏洞的修复建议通常包括以下几个方面：

升级Java版本：确保Java环境使用的是最新版本，因为Oracle会定期发布安全更新和补丁来修复已知漏洞。

使用安全的反序列化库：如果可能，使用经过安全审查的第三方库来处理反序列化操作，这些库可能提供了更安全的反序列化机制。

限制反序列化操作：尽量避免在应用程序中使用反序列化，特别是在处理不可信数据时。如果必须使用，确保只反序列化来自可信来源的数据。

使用白名单：在反序列化过程中，使用白名单来限制可以反序列化的类。不要允许反序列化未知或不受信任的类。

自定义类加载器：使用自定义类加载器来控制类加载过程，确保只有特定的类可以被加载。

禁用危险的Java序列化：如果可能，考虑使用其他序列化机制，如JSON、XML或Google的Protocol Buffers等，这些机制不涉及Java的类加载机制。

使用ObjectInputFilter：Java 9引入了ObjectInputFilter，允许你指定一个过滤器来限制可以反序列化的类。

使用-Djava.io.SerializableFilter：Java 11引入了-Djava.io.SerializableFilter选项，可以用来限制反序列化过程中允许的类。

避免使用Serializable：考虑使用其他接口或自定义序列化方法，避免使用Java的Serializable接口。

清理输入数据：在反序列化之前，对输入数据进行清理，以去除可能的恶意代码。

使用安全的配置：确保Java安全配置是安全的，例如设置java.security属性来限制类加载。

使用其他序列化方式：在数据的传输中使用 protobuf、json、thrift等其他序列化方式来替代 java 序列化，通常有更好的安全性。

Chanzi-Separator
*/
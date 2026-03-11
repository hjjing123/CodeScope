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
  // com.xxl.rpc.serialize.impl.HessianSerializer#deserialize
  ('deserialize' IN sinkNode.selectors AND  sinkNode.type='HessianSerializer')
MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer','int','long'] )
RETURN
  p AS path

/*
Chanzi-Separator

Hessian反序列化漏洞

漏洞原理
Hessian 是一种轻量级的二进制RPC协议，用于实现跨语言的远程调用。Hessian 反序列化漏洞主要源于其在反序列化过程中对输入数据的处理不当，导致攻击者可以通过构造恶意输入数据来触发漏洞。

任意类反序列化

Hessian 在反序列化时，会根据输入流中的类型信息来选择对应的反序列化器。如果攻击者能够控制输入流中的类型信息，Hessian 可能会尝试反序列化任意类，即使这些类没有实现Serializable接口。

Hessian 提供了一个_isAllowNonSerializable变量，允许反序列化未实现Serializable接口的类。这使得攻击者可以构造恶意类并绕过常规的序列化检查。

Map 类型的利用

Hessian 在处理Map类型数据时，会调用Map的put方法将键值对写入。对于HashMap，put方法会调用键的hashCode方法来判断是否有重复的键；对于TreeMap，则会调用compareTo方法。

攻击者可以通过构造恶意类，重写hashCode、equals或compareTo方法，在反序列化时触发这些方法，从而实现任意代码执行。

不受限的反序列化器

Hessian 默认使用UnsafeDeserializer来反序列化自定义类型数据。这种反序列化器不会对类的来源和安全性进行严格检查，导致攻击者可以利用恶意类来执行恶意代码。

Chanzi-Separator
为了防止Hessian反序列化漏洞，可以采取以下措施：

限制反序列化类型

明确指定允许反序列化的类，避免反序列化任意类。可以通过白名单机制限制反序列化的类范围，只允许反序列化已知安全的类。

禁用_isAllowNonSerializable变量，确保只有实现了Serializable接口的类才能被反序列化。

自定义反序列化器

为关键类实现自定义的反序列化器，确保反序列化过程的安全性。自定义反序列化器可以在反序列化时对输入数据进行严格校验，防止恶意数据的注入。

输入数据校验

在反序列化之前，对输入数据进行严格的校验，确保数据的合法性和完整性。可以通过正则表达式、数据格式验证等方式，过滤掉可能的恶意输入。

更新Hessian库

使用最新版本的Hessian库，以获取官方的安全修复。新版本的Hessian可能已经修复了已知的反序列化漏洞，或者提供了更安全的反序列化机制。

启用安全审计

在反序列化过程中启用安全审计，记录反序列化操作的详细信息。通过审计日志，可以及时发现异常的反序列化行为，并采取相应的措施。

限制反序列化深度

设置反序列化的深度限制，防止攻击者通过嵌套的恶意数据结构导致资源耗尽。这可以有效防止拒绝服务攻击（DoS）。

通过以上措施，可以有效降低Hessian反序列化漏洞的风险，保护系统的安全性。
Chanzi-Separator
*/
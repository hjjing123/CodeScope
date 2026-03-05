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
  (sinkNode.selector='readObject'  AND  sinkNode.type='XMLDecoder')
MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
    WHERE NONE(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer'] )

RETURN
  p AS path

/*
Chanzi-Separator

XMLDecoder反序列化漏洞

XMLDecoder反序列化漏洞简介，XMLDecoder反序列化漏洞主要出现在使用Java的XMLDecoder类处理外部输入的XML数据时。由于XMLDecoder在反序列化XML数据时，会根据XML中指定的类信息动态实例化对象，若攻击者能够控制XML内容，构造特定的XML结构，就可以利用Java反射机制执行任意代码，导致远程代码执行（RCE）漏洞。

漏洞涉及的组件

XMLDecoder反序列化漏洞主要涉及的组件是Java自带的XMLDecoder类，它用于将XML格式的数据反序列化为Java对象。

此外，该漏洞在Oracle WebLogic Server中被广泛利用，因为WebLogic Server的WLS Security组件对外提供的webservice服务中使用了XMLDecoder来解析用户传入的XML数据，导致了多个高危RCE漏洞，如CVE-2017-3506、CVE-2017-10271、CVE-2019-2725、CVE-2019-2729等。

反序列化漏洞示例

以下是一个简单的XMLDecoder反序列化漏洞的示例：

xml
<java>
    <object class="java.lang.ProcessBuilder">
        <array class="java.lang.String" length="1">
            <void index="0">
                <string>calc.exe</string>
            </void>
        </array>
        <void method="start"/>
    </object>
</java>

当上述XML数据被XMLDecoder反序列化时，它会创建一个ProcessBuilder对象，并执行calc.exe（Windows下的计算器程序）。

漏洞成因

XMLDecoder反序列化漏洞的成因在于XMLDecoder处理节点时，信任了外部输入的XML指定节点类型信息（class类型节点），同时在进行节点实例化的时候允许节点属性由XML任意控制，导致Expression的set()方法被重载为风险函数（例如start），由于Java反射特性实现了代码执行。

Chanzi-Separator

1. 禁用或移除XMLDecoder的使用：如果可能，应考虑在应用程序中禁用或移除XMLDecoder的使用，特别是在处理不受信任的输入时。这是因为XMLDecoder在反序列化XML数据时存在安全风险，可能会导致远程代码执行。

2. 输入验证和过滤：对所有外部输入进行严格的验证和过滤，确保不允许执行恶意代码。对于XMLDecoder处理的数据，应确保其来源可靠，并且内容符合预期的格式和结构。

3. 使用其他序列化方式：在数据的传输中使用 protobuf、json、thrift等其他序列化方式来替代 java 序列化，通常有更好的安全性。

Chanzi-Separator
*/
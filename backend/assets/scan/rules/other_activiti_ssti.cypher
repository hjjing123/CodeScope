MATCH
  (sourceNode)
  WHERE
  (
  // jfinal : String keyword=this.getPara("keyword");
  (sourceNode:CallArg AND 'getPara' IN  sourceNode.selectors) OR
  sourceNode.assignRight STARTS WITH 'getParamsMap' OR
  sourceNode.assignRight STARTS WITH 'getParaMap' OR
  // 一些框架自定义注解， 请求入参使用 @HttpParam + Argument标签匹配方法形参，形式上定义在接口、实际上入口在实现类，所以用 MethodBinding
  (sourceNode:MethodBinding AND 'HttpParam' IN sourceNode.paramAnnotations)
  ) AND
  NOT sourceNode.type  IN ['Long', 'Integer', 'HttpServletResponse']

MATCH
  (sinkNode)
  WHERE
  // 保存模型
  ('saveModel' IN sinkNode.selectors AND 'RepositoryService' IN sinkNode.receiverTypes) OR
  // 启动模型部署后的流程
  ('startProcessInstanceByKey' IN sinkNode.selectors AND 'RuntimeService' IN sinkNode.receiverTypes)

MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
  WHERE none(n IN nodes(p)
    WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer', 'int', 'long'])
RETURN
  p AS path

/*
Chanzi-Separator

activiti 模型注入

Activiti是一个开源的工作流和业务流程管理（BPM）平台，它基于BPMN 2.0规范。Activiti可以用来创建、执行和管理业务流程，并且与Spring框架紧密集成，支持流程的建模、执行和监控。

Activiti的Model指的是在Activiti中定义的业务流程模型，它通常以BPMN（Business Process Model and Notation）格式存在。

这些模型可以被设计、部署到Activiti引擎中，并被执行。Model包含了流程定义的所有信息，包括流程中的任务、决策点、参与者等。

如果Activiti的Model被外部控制或修改，可能会带来以下安全风险：

1. 流程篡改：恶意用户可能修改流程模型，改变业务流程的执行逻辑，导致业务流程不符合预期。

2. 数据泄露：如果流程模型中包含了敏感信息，未经授权的修改可能导致这些信息泄露。

3. 服务拒绝（DoS）：恶意的流程模型可能会消耗过多的系统资源，导致Activiti引擎无法处理正常的业务流程，从而形成服务拒绝攻击。

4. 代码执行：如果Activiti配置不当，攻击者可能通过流程模型中的恶意代码执行远程代码，这可能导致服务器被控制或数据被破坏，这种情况被称为远程代码执行（RCE）。

5. 权限绕过：攻击者可能通过修改流程模型来绕过正常的权限检查，从而访问或执行他们本无权进行的操作。

示例：
以下是一个模型的例子，在BPMN 2.0中，可以通过脚本任务（Script Task）执行脚本代码。如果这些脚本代码是由用户输入的，并且没有经过适当的验证和清理，那么恶意用户可能会注入并执行恶意代码。
<bpmn:process id="scriptProcess" isExecutable="true">
    <bpmn:startEvent id="start" />
    <bpmn:sequenceFlow id="flow1" sourceRef="start" targetRef="script" />
    <bpmn:scriptTask id="script" scriptFormat="groovy">
        <bpmn:script>System.setProperty("user.language", "fr");</bpmn:script>
    </bpmn:scriptTask>
    <bpmn:endEvent id="end" />
    <bpmn:sequenceFlow id="flow2" sourceRef="script" targetRef="end" />
</bpmn:process>

参考：https://www.activiti.org/userguide/#api.services.deployment

Chanzi-Separator

为了减少这些安全风险，应该采取以下措施：

输入校验：应避免将用户的输入直接作为activiti的模型或模型的一部分，如果需要这样做请务必对输入的内容进行校验，防止插入恶意脚本。

权限控制：确保只有授权的用户才能修改流程模型。

模型验证：在部署流程模型之前，验证模型的完整性和安全性。

定期审计：定期审计流程模型和Activiti的配置，确保没有未授权的更改。

使用最新的Activiti版本：确保使用的Activiti版本是最新的，以利用最新的安全修复和功能。

限制流程模型的功能：避免在流程模型中使用不必要的复杂功能，减少潜在的攻击面。

Chanzi-Separator
*/
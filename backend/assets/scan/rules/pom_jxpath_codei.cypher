MATCH
  (sinkNode:PomDependency|GradleDependency)
  WHERE
  sinkNode.groupId = 'commons-jxpath' AND   sinkNode.artifactId = 'commons-jxpath' AND   sinkNode.realVersion < '1.4.0'
RETURN
  sinkNode AS path

/*
Chanzi-Separator

Apache Commons JXPath远程代码执行漏洞

Apache Commons JXPath 是一个基于 Java 的 XPath 1.0 实现库，允许使用 XPath 表达式遍历 Java 对象图（如 JavaBeans、Map、DOM 等）。

该组件存在一个严重的远程代码执行漏洞（RCE），编号为 CVE-2022-41852，CVSS 评分 9.8

漏洞成因

使用 JXPathContext 类中的方法（如 getValue()、iterate() 等）处理不受信任的 XPath 表达式时，未对表达式做安全限制。

攻击者可构造 XPath 表达式，通过反射机制加载并执行任意 Java 类（如 Runtime.exec()），实现远程命令执行。

受影响版本范围 ： Apache Commons JXPath	≤ 1.3（包括 1.3 及更早版本）

Chanzi-Separator

替换组件：Apache 官方已停止维护 JXPath，建议迁移至其他 XPath 实现库（如 Saxon、Jaxen）。

Chanzi-Separator
*/
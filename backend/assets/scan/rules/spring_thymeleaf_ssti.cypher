// spring mvc ,使用 模版引擎渲染， 直接返回String 或者 ModelAndView 的情况；排除掉直接返回json的情况
// 1. **匹配节点`t`**：首先，我们尝试匹配具有特定`groupId`和`artifactId`的`PomDependency`或`GradleDependency`节点。
MATCH
  (t:PomDependency|GradleDependency)
WHERE
t.groupId = 'org.springframework.boot' AND t.artifactId = 'spring-boot-starter-thymeleaf'

WITH
  t

// 2. **可选匹配`sourceNode`**：如果`t`节点存在，我们接下来尝试匹配`SpringControllerArg`节点，这些节点的类型不是`Long`或`Integer`，并且具有特定的注解。
OPTIONAL MATCH
  (sourceNode:SpringControllerArg)
  WHERE sourceNode.type <> 'Long' AND sourceNode.type <> 'Integer' AND
  NOT 'RestController' IN sourceNode.classAnnotations AND
  NOT 'ResponseBody' IN sourceNode.methodAnnotations

// 3. **可选匹配`sinkNode`**：然后，我们尝试匹配`ReturnArg`节点。
OPTIONAL MATCH
  (sinkNode:ReturnArg)
  WHERE sinkNode.type = 'String'

// 4. **可选匹配路径`p`**：如果`sourceNode`和`sinkNode`都存在，我们计算它们之间的最短路径，排除路径中包含特定类型的节点。
OPTIONAL MATCH
  p = shortestPath((sourceNode)-[*..10]->(sinkNode))
  WHERE none(n IN nodes(p)
    WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer','int','long'])
// 5. **收集路径**：我们将所有找到的路径收集到一个列表`paths`中。
WITH
  t, collect(p) AS paths
  WHERE t IS NOT NULL

// 6. **返回结果**：如果`t`节点存在，我们返回路径列表`paths`；如果`t`节点不存在，我们返回一个空列表。
// 这个查询确保了只有在`t`节点存在时才会执行路径查询，并且正确地处理了存在和不存在`t`节点的情况。
RETURN
  CASE
    WHEN t IS NOT NULL THEN paths
    ELSE []
    END AS path

/*
Chanzi-Separator

springboot Thymeleaf 模板注入

Thymeleaf 是一种现代的服务器端 Java 模板引擎：它允许在 HTML、XML、JavaScript、CSS 等文件中处理模板，使这些文件既能作为模板使用，又能作为静态原型展示。它与 Spring 框架有很好的集成，广泛应用于 Java Web 开发中。

Spring Boot中使用Thymeleaf作为模板引擎时，存在模板注入漏洞（也称为SSTI - Server-Side Template Injection）的原理主要涉及以下几个方面：

1. 视图渲染过程：
   - 在Spring Boot中，当控制器（Controller）返回一个字符串作为视图名称时，这个字符串会被传递给Thymeleaf模板引擎进行解析和渲染。

2. 表达式解析：
   - Thymeleaf在渲染过程中会解析视图名称中的表达式。如果视图名称中包含了SpEL（Spring Expression Language）表达式，Thymeleaf会尝试执行这些表达式。

3. 可控的视图名称：
   - 如果攻击者能够控制控制器返回的视图名称，或者能够通过URL路径参数控制视图名称，那么他们就可以注入恶意的SpEL表达式。

4. 片段表达式：
   - Thymeleaf支持片段表达式，格式为`~{templatename :: selector}`。如果用户能够控制`templatename`或`selector`，就可能注入恶意代码。

5. 漏洞成因：
   - 漏洞成因主要是Thymeleaf对`templatename`的过滤/管控不严，导致攻击者可以利用控制器返回的模板名执行SpEL表达式。

6. 漏洞利用：
   - 攻击者通过构造特殊的输入，如`__${new java.util.Scanner(T(java.lang.Runtime).getRuntime().exec("cmd")}__::.x`，可以触发Thymeleaf解析SpEL表达式，进而执行系统命令。

7. 漏洞影响：
   - 这种类型的注入攻击可以导致远程代码执行（RCE），使攻击者能够完全控制服务器并访问敏感数据。

综上所述，Thymeleaf模板注入漏洞的原理是基于Thymeleaf模板引擎对用户可控输入的表达式解析，如果这些输入没有得到正确的过滤和转义，就可能导致服务器端的代码执行，从而引发安全问题。

参考： https://paper.seebug.org/1332/#_3

Chanzi-Separator

以下是一些修复 Thymeleaf 模板注入漏洞的方法：

修复方案

针对Spring Boot中Thymeleaf模板注入漏洞的修复方案，主要有以下几种方法：

1. 设置@ResponseBody注解：
   如果控制器方法返回值上使用了`@ResponseBody`注解，Spring将返回值作为响应体处理，而不是视图名称，因此不会进行模板注入攻击。例如：
   ```java
   @GetMapping("/safe/fragment")
   @ResponseBody
   public String safeFragment(@RequestParam String section) {
       return "welcome :: " + section;
   }
   ```

2. 设置重定向redirect：
   当视图名称以`redirect:`前缀开头时，Spring不再使用ThymeleafView解析，而是使用RedirectView解析，该视图不会执行表达式。例如：
   ```java
   @GetMapping("/safe/redirect")
   public String redirect(@RequestParam String url) {
       return "redirect:" + url;
   }
   ```

3. 设置response响应：
   如果控制器方法参数中包含`HttpServletResponse`，Spring认为已经处理了HTTP响应，因此视图名称解析就不会发生。例如：
   ```java
   @GetMapping("/safe/doc/{document}")
   public void getDocument(@PathVariable String document, HttpServletResponse response) {
       log.info("Retrieving " + document);
   }
   ```
4. 升级Thymeleaf版本：
   Thymeleaf在3.0.12及以后的版本中增加了多处安全机制来防护模板注入漏洞，因此升级到最新版本的Thymeleaf也是一个有效的修复措施。

5. 输入验证和清理：
   对所有用户输入进行严格的验证和清理，确保不允许任何可能导致模板注入的输入通过。

6. 使用安全的模板语法：
   避免在模板名称中直接使用用户输入，或者确保用户输入被正确地转义，以防止注入攻击。

通过上述方法，可以有效地修复和防护Spring Boot中Thymeleaf模板注入漏洞。

Chanzi-Separator
*/
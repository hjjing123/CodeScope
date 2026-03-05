MATCH// pom 的版本号可能是放在 properties标签里的， dependence标签里使用${xxx.version} 的方式引入
// 所以 sink点的version 是 ${xxx.version} ，而 realVersion才是真实的版本号
  (sinkNode:PomDependency|GradleDependency)
  WHERE
  sinkNode.groupId = 'org.springframework.cloud' AND   sinkNode.artifactId = 'spring-cloud-gateway-server' AND   sinkNode.realVersion < '3.1.1'
RETURN
  sinkNode AS path

/*
Chanzi-Separator

spring gateway远程代码执行漏洞

Spring Cloud Gateway 是一个基于 Spring Boot 2.x 和 Project Reactor 构建的 API 网关，它旨在为微服务架构提供一种简单、有效、统一的 API 路由管理方式。然而，如搜索结果所示，Spring Cloud Gateway 也存在一些安全漏洞，其中较为严重的是 CVE-2022-22947，这是一个远程代码执行漏洞。

CVE-2022-22947 漏洞概述：
该漏洞发生在当 Spring Cloud Gateway 启用并暴露 Gateway Actuator 端点时，攻击者可以发送特制的恶意请求，执行 SpEL（Spring Expression Language）表达式，从而在目标服务器上执行任意代码。

影响版本：

Spring Cloud Gateway 3.1.x < 3.1.1
Spring Cloud Gateway 3.0.x < 3.0.7
其他旧的、不受支持的 Spring Cloud Gateway 版本。

攻击者可以通过构造恶意的 HTTP 请求，添加包含恶意 Filter 的路由，当这些路由被刷新并应用时，恶意的 SpEL 表达式被执行，导致远程代码执行。

其他漏洞：
除了 CVE-2022-22947，Spring Cloud Gateway 还可能受到其他漏洞的影响，如 CVE-2021-22051，这是一个请求漏洞，允许特定制作的请求可能使下游服务产生额外的请求 。

总的来说，使用 Spring Cloud Gateway 的开发者应该密切关注官方的安全公告，并及时应用安全补丁和升级，以确保系统的安全性。同时，合理配置 Spring Security 可以提供额外的安全层，保护网关免受未授权访问和攻击。
Chanzi-Separator

官方已经发布了修复补丁，建议用户升级到安全版本：
3.1.x 版本用户应升级到 3.1.1+ 版本
3.0.x 版本用户应升级到 3.0.7+ 版本
如果不需要 Gateway Actuator 端点，可以通过配置 management.endpoint.gateway.enabled 设置为 false 来禁用它。
如果需要 Actuator 端点，则应使用 Spring Security 对其进行保护
。
Chanzi-Separator
*/
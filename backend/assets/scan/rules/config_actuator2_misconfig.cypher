MATCH
  (sinkNode:YmlKeyValue|PropertiesKeyValue)
WHERE
sinkNode.name = 'management.security.enabled' AND sinkNode.value = 'false'

RETURN
  sinkNode AS path
/*
Chanzi-Separator

Spring Boot Actuator 未授权访问漏洞

漏洞的原理是，当应用程序使用了 Spring Boot Actuator 进行监控和管理，但未对 Actuator 提供的端点（Endpoints）进行适当的安全配置时，攻击者可以利用这些端点获取敏感信息或执行未授权的操作。以下是一些关键的安全风险和漏洞利用方式：

敏感信息泄露：未授权访问者可以通过 /heapdump、/metrics、/env 等端点获取敏感信息，如数据库账户密码、应用配置、代码等 。

执行恶意操作：攻击者可以通过未授权访问执行操作，如通过 /restart 重启应用程序、通过 /shutdown 关闭应用程序 。

远程代码执行：如果配置不当，使用 Jolokia 库特性可以远程执行任意代码，获取服务器权限 。

内存信息泄露：通过 /heapdump 端点可以下载应用的堆转储文件，可能包含内存中的敏感信息，比如数据库密码、其他密钥等。

日志泄露：通过 /logfile 端点可以输出日志文件的内容，可能包含敏感数据 。

监控信息泄露：通过 /metrics 端点可以获取应用的性能指标，可能包含敏感业务数据 。

参考：https://docs.spring.io/spring-boot/reference/actuator/endpoints.html

Chanzi-Separator

Spring Boot Actuator 未授权访问漏洞是一个严重的安全问题，它可能允许未授权的用户访问敏感的监控和管理端点。以下是一些修复该漏洞的方案：

限制端点暴露：在 application.properties 或 application.yml 配置文件中，限制暴露的端点列表。只包含必要的端点，并排除所有其他端点，特别是那些可能暴露敏感信息的端点。

properties
management.endpoints.web.exposure.include=health,info
management.endpoints.web.exposure.exclude=env,beans,metrics
参考
。

启用 Spring Security：通过整合 Spring Security 来保护 Actuator 端点。确保只有经过身份验证和授权的用户才能访问这些端点。

java
@Override
protected void configure(HttpSecurity http) throws Exception {
    http
        .authorizeRequests()
        .antMatchers("/actuator/**").hasRole("ACTUATOR")
        .anyRequest().authenticated()
        .and()
        .httpBasic();
}
参考 。

配置防火墙规则：在网络层面上，通过配置防火墙规则来阻止对 Actuator 端点的外部访问。

自定义端点安全性：如果需要更细粒度的控制，可以为每个端点自定义安全性配置。

使用 HTTPS：确保所有的端点通信都是通过 HTTPS 进行的，以防止中间人攻击。

禁用敏感端点：对于不需要的端点，如 /shutdown、/heapdump 和 /env，应该明确禁用它们。

properties
management.endpoint.shutdown.enabled=false

定期更新：保持 Actuator 和 Spring Boot 的版本更新，以利用最新的安全修复。

审计日志：设置详细的审计日志，以便在发生未授权访问时能够追踪和调查。

使用IP限制：如果可能，限制访问端点的IP地址。

完全禁用 Actuator：如果不需要 Actuator 功能，可以完全移除相关依赖或配置禁用所有端点。

选择适合你应用程序需求和安全策略的修复方案，并确保正确实施。

Chanzi-Separator
*/
MATCH
  (sinkNode:YmlKeyValue|PropertiesKeyValue)
WHERE
// 核心配置项：暴露的端点（主配置项，保留原逻辑）
(sinkNode.name = 'management.endpoints.web.exposure.include' AND
(sinkNode.value = '*' OR  // 高危：暴露所有端点
sinkNode.value CONTAINS 'heapdump' OR  // 泄露内存快照
sinkNode.value CONTAINS 'beans' OR  // 泄露Spring Bean结构
sinkNode.value CONTAINS 'caches' OR  // 泄露缓存配置
sinkNode.value CONTAINS 'configprops' OR  // 泄露配置属性（含敏感配置）
sinkNode.value CONTAINS 'env' OR  // 泄露环境变量（高危，含密钥/数据库连接）
sinkNode.value CONTAINS 'loggers' OR  // 可修改日志级别
sinkNode.value CONTAINS 'restart' OR  // 远程重启应用（高危）
sinkNode.value CONTAINS 'threaddump' OR  // 泄露线程信息
sinkNode.value CONTAINS 'metrics' OR  // 泄露系统/业务指标
sinkNode.value CONTAINS 'scheduledtasks' OR  // 泄露定时任务
sinkNode.value CONTAINS 'mappings' OR  // 泄露URL路由映射
sinkNode.value CONTAINS 'prometheus' OR  // 监控指标（虽合规但需限制访问）
sinkNode.value CONTAINS 'logfile' OR  // 泄露日志内容（可能含敏感数据）
sinkNode.value CONTAINS 'liquibase' OR  // 泄露数据库迁移记录
sinkNode.value CONTAINS 'flyway' OR  // 泄露数据库版本控制记录
sinkNode.value CONTAINS 'sessions' OR  // 泄露会话信息（若未脱敏）
sinkNode.value CONTAINS 'shutdown' OR  // 远程关闭应用（高危）
sinkNode.value CONTAINS 'httptrace' OR  // 泄露HTTP请求轨迹（含参数/Cookie）
sinkNode.value CONTAINS 'integrationgraph' OR  // 泄露集成流程
sinkNode.value CONTAINS 'quartz' OR  // 泄露Quartz定时任务
sinkNode.value CONTAINS 'jolokia' OR  // JMX暴露（可执行MBean操作，高危）
sinkNode.value CONTAINS 'auditevents')) OR  // 泄露审计事件

// 补充1：排除配置失效场景（若"exclude"未覆盖高危端点，仍有风险）
(sinkNode.name = 'management.endpoints.web.exposure.exclude' AND
NOT (sinkNode.value CONTAINS 'env' OR  // 未排除env（高危）
sinkNode.value CONTAINS 'shutdown' OR  // 未排除shutdown（高危）
sinkNode.value CONTAINS 'restart' OR  // 未排除restart（高危）
sinkNode.value CONTAINS 'jolokia')) OR  // 未排除jolokia（高危）

// 补充2：非Web端点（如JMX）暴露风险（易被忽略）
(sinkNode.name = 'management.endpoints.jmx.exposure.include' AND
(sinkNode.value = '*' OR  // JMX暴露所有端点（可通过JConsole远程操作）
sinkNode.value CONTAINS 'env' OR
sinkNode.value CONTAINS 'shutdown')) OR

// 补充3：Actuator基础路径配置（若未修改默认路径，易被扫描）
(sinkNode.name = 'management.endpoints.web.base-path' AND
(sinkNode.value = '/actuator' OR  // 使用默认路径（无自定义前缀，易暴露）
sinkNode.value IS null OR  // 未配置，默认使用/actuator
sinkNode.value = '')) OR

// 补充4：Actuator启用状态（若全局启用且未限制访问）
(sinkNode.name = 'management.endpoints.enabled-by-default' AND
sinkNode.value = 'true')  // 默认启用所有端点（即使未显式暴露，仍有启用风险）

RETURN
  sinkNode AS path

/*
Chanzi-Separator

Spring Boot Actuator 未授权访问漏洞

漏洞的原理是，当应用程序使用了 Spring Boot Actuator 进行监控和管理，但未对 Actuator 提供的端点（Endpoints）进行适当的安全配置时，攻击者可以利用这些端点获取敏感信息或执行未授权的操作。

以下是一些关键的安全风险和漏洞利用方式：

敏感信息泄露：未授权访问者可以通过 /heapdump、/metrics、/env 等端点获取敏感信息，如数据库账户密码、应用配置、代码等 。

执行恶意操作：攻击者可以通过未授权访问执行操作，如通过 /restart 重启应用程序、通过 /shutdown 关闭应用程序 。

远程代码执行：如果配置不当，使用 Jolokia 库特性可以远程执行任意代码，获取服务器权限 。

内存信息泄露：通过 /heapdump 端点可以下载应用的堆转储文件，可能包含内存中的敏感信息，比如数据库密码、其他密钥等 。

日志泄露：通过 /logfile 端点可以输出日志文件的内容，可能包含敏感数据 。

监控信息泄露：通过 /metrics 端点可以获取应用的性能指标，可能包含敏感业务数据 。

参考：https://docs.spring.io/spring-boot/reference/actuator/endpoints.html

Chanzi-Separator

Spring Boot Actuator 未授权访问漏洞是一个严重的安全问题，它可能允许未授权的用户访问敏感的监控和管理端点。以下是一些修复该漏洞的方案：

限制端点暴露：在 application.properties 或 application.yml 配置文件中，限制暴露的端点列表。只包含必要的端点，并排除所有其他端点，特别是那些可能暴露敏感信息的端点。

properties：
management.endpoints.web.exposure.include=health,info
management.endpoints.web.exposure.exclude=env,beans,metrics

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

配置防火墙规则：在网络层面上，通过配置防火墙规则来阻止对 Actuator 端点的外部访问。

自定义端点安全性：如果需要更细粒度的控制，可以为每个端点自定义安全性配置。

使用 HTTPS：确保所有的端点通信都是通过 HTTPS 进行的，以防止中间人攻击。

禁用敏感端点：对于不需要的端点，如 /shutdown、/heapdump 和 /env，应该明确禁用它们。

properties：
management.endpoint.shutdown.enabled=false

定期更新：保持 Actuator 和 Spring Boot 的版本更新，以利用最新的安全修复。

审计日志：设置详细的审计日志，以便在发生未授权访问时能够追踪和调查。

使用IP限制：如果可能，限制访问端点的IP地址。

完全禁用 Actuator：如果不需要 Actuator 功能，可以完全移除相关依赖或配置禁用所有端点。

选择适合你应用程序需求和安全策略的修复方案，并确保正确实施。

Chanzi-Separator
*/
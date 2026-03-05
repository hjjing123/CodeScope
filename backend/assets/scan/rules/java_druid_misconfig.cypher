MATCH
  (sinkNode:TrueLiteral)
WHERE
('setEnabled' IN sinkNode.selectors AND  'StatViewServlet' IN  sinkNode.receiverTypes)

RETURN
  sinkNode AS path
/*
Chanzi-Separator

druid监控页面未授权访问

StatViewServlet 的 enabled 是 Spring Boot 中 Druid 数据库连接池配置的一个属性，用于控制是否启用 Druid 的监控统计功能中的 StatViewServlet。这个属性的启用会带来一些安全风险，主要包括：

未授权访问风险：默认情况下，如果启用了 StatViewServlet，它可能会暴露敏感的监控信息，如数据库访问详情、慢查询记录等，而没有任何身份验证措施。这意味着任何人都可以访问这些监控页面，获取系统内部信息，可能导致数据泄露或被恶意利用。

信息泄露：监控页面可以展示数据库的实时状态、活跃连接数、查询执行时间等关键信息。未经授权的用户如果能够访问这些信息，可能会对系统的安全性和稳定性造成威胁。

系统稳定性风险：攻击者可以利用监控页面的信息来发起更有针对性的攻击，比如通过分析慢查询来找到可能的注入点，或者通过监控数据来推测系统的负载情况，从而发起拒绝服务攻击（DoS）。

Chanzi-Separator


为了降低这些风险，可以采取以下措施：

启用身份验证：在 Druid 的监控配置中设置用户名和密码，确保只有授权用户才能访问监控页面。可以通过在 application.yml 或 application.properties 文件中配置 spring.datasource.druid.stat-view-servlet.login-username 和 spring.datasource.druid.stat-view-servlet.login-password 来实现。

限制访问 IP：配置 IP 白名单（allow）和黑名单（deny），以控制哪些 IP 地址可以访问监控页面。例如，只允许特定的管理IP访问监控页面。

关闭重置功能：Druid 监控页面提供了一个“Reset All”功能，允许用户重置统计数据。这可能会被恶意用户利用来清除监控数据，隐藏攻击痕迹。可以通过设置 spring.datasource.druid.stat-view-servlet.reset-enable=false 来禁用此功能。

完全禁用监控页面：如果不使用 Druid 的监控功能，可以完全禁用 StatViewServlet，以避免任何潜在的安全风险。可以通过设置 spring.datasource.druid.stat-view-servlet.enabled=false 来实现。

通过这些措施，可以有效地提高系统的安全性，防止未授权访问和信息泄露。

Chanzi-Separator
*/
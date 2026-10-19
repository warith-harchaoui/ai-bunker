Feature: Global

  Generated from the shipped rules by `ai-bunker spec --export`.
  Scenarios written by hand below the generated ones are run too, and
  are the ones that can fail: they assert behaviour nobody derived
  from the implementation.

  # global.generic_secret -- BLOCKER
  # An API key, token or password must never enter the model's context.

  Scenario: global.generic_secret catches api_key = "sk_live_8Kq2mZx9PvN3wR7t"
    Given a tool result containing "api_key = \"sk_live_8Kq2mZx9PvN3wR7t\""
    When the gateway screens it
    Then the rule global.generic_secret fires
    And the text is redacted

  Scenario: global.generic_secret catches API_KEY: ghp_A7kQm2Zx9PvN3wR7tJ4hB6nC8dF1gH
    Given a tool result containing "API_KEY: ghp_A7kQm2Zx9PvN3wR7tJ4hB6nC8dF1gH"
    When the gateway screens it
    Then the rule global.generic_secret fires
    And the text is redacted

  Scenario: global.generic_secret catches password=7Hk2Lm9Qw3Er5Ty8Ui0Op1As
    Given a tool result containing "password=7Hk2Lm9Qw3Er5Ty8Ui0Op1As"
    When the gateway screens it
    Then the rule global.generic_secret fires
    And the text is redacted

  Scenario: global.generic_secret catches aws_secret_access_key = hT3kQm9ZxPvN3wR7tJ4hB6nC...
    Given a tool result containing "aws_secret_access_key = hT3kQm9ZxPvN3wR7tJ4hB6nC8dF1gKs2LpQr5Yz0"
    When the gateway screens it
    Then the rule global.generic_secret fires
    And the text is redacted

  Scenario: global.generic_secret catches AWS_SECRET_ACCESS_KEY=hT3kQm9ZxPvN3wR7tJ4hB6nC8d...
    Given a tool result containing "AWS_SECRET_ACCESS_KEY=hT3kQm9ZxPvN3wR7tJ4hB6nC8dF1gKs2LpQr5Yz0"
    When the gateway screens it
    Then the rule global.generic_secret fires
    And the text is redacted

  Scenario: global.generic_secret catches secret=hT3k/Qm9Zx+PvN3wR7tJ4hB6nC8dF1gKs2LpQ/r5Y...
    Given a tool result containing "secret=hT3k/Qm9Zx+PvN3wR7tJ4hB6nC8dF1gKs2LpQ/r5Yz0"
    When the gateway screens it
    Then the rule global.generic_secret fires
    And the text is redacted

  Scenario: global.generic_secret leaves api_key = "REPLACE_ME_WITH_YOUR_KEY" alone
    Given a tool result containing "api_key = \"REPLACE_ME_WITH_YOUR_KEY\""
    When the gateway screens it
    Then no rule fires

  Scenario: global.generic_secret leaves token: "<your-token-here>" alone
    Given a tool result containing "token: \"<your-token-here>\""
    When the gateway screens it
    Then no rule fires

  Scenario: global.generic_secret leaves api_key = xxxxxxxxxxxxxxxxxxxx alone
    Given a tool result containing "api_key = xxxxxxxxxxxxxxxxxxxx"
    When the gateway screens it
    Then no rule fires

  Scenario: global.generic_secret leaves token_count = 4096 alone
    Given a tool result containing "token_count = 4096"
    When the gateway screens it
    Then no rule fires

  Scenario: global.generic_secret leaves api_key = os.environ['API_KEY'] alone
    Given a tool result containing "api_key = os.environ['API_KEY']"
    When the gateway screens it
    Then no rule fires

  Scenario: global.generic_secret leaves secret_key_file = /etc/ssl/private/server.key alone
    Given a tool result containing "secret_key_file = /etc/ssl/private/server.key"
    When the gateway screens it
    Then no rule fires

  # global.vendor_token -- BLOCKER
  # A credential with a known vendor prefix appeared in a tool output.

  Scenario: global.vendor_token catches ghp_hT3kQm9ZxPvN3wR7tJ4hB6nC8dF1gKs2LpQr
    Given a tool result containing "ghp_hT3kQm9ZxPvN3wR7tJ4hB6nC8dF1gKs2LpQr"
    When the gateway screens it
    Then the rule global.vendor_token fires
    And the text is redacted

  Scenario: global.vendor_token catches remote: https://ghp_hT3kQm9ZxPvN3wR7tJ4hB6nC8dF1...
    Given a tool result containing "remote: https://ghp_hT3kQm9ZxPvN3wR7tJ4hB6nC8dF1gKs2LpQr@github.com/o/r"
    When the gateway screens it
    Then the rule global.vendor_token fires
    And the text is redacted

  Scenario: global.vendor_token catches xoxb-NOT-A-REAL-SLACK-TOKEN-FOR-TESTS-ONLY
    Given a tool result containing "xoxb-NOT-A-REAL-SLACK-TOKEN-FOR-TESTS-ONLY"
    When the gateway screens it
    Then the rule global.vendor_token fires
    And the text is redacted

  Scenario: global.vendor_token catches AIzaSyB1cD3fG5hJ7kL9mN1pQ3rS5tU7vW9xY1z
    Given a tool result containing "AIzaSyB1cD3fG5hJ7kL9mN1pQ3rS5tU7vW9xY1z"
    When the gateway screens it
    Then the rule global.vendor_token fires
    And the text is redacted

  Scenario: global.vendor_token leaves the ghp_ prefix marks a GitHub personal access t... alone
    Given a tool result containing "the ghp_ prefix marks a GitHub personal access token"
    When the gateway screens it
    Then no rule fires

  Scenario: global.vendor_token leaves sk-123 alone
    Given a tool result containing "sk-123"
    When the gateway screens it
    Then no rule fires

  Scenario: global.vendor_token leaves xoxb-short alone
    Given a tool result containing "xoxb-short"
    When the gateway screens it
    Then no rule fires

  Scenario: global.vendor_token leaves AIza alone
    Given a tool result containing "AIza"
    When the gateway screens it
    Then no rule fires

  # global.private_key -- BLOCKER
  # A private key block appeared in a tool output.

  Scenario: global.private_key catches -----BEGIN RSA PRIVATE KEY----- MIIEpAIBAAKCA --...
    Given a tool result containing "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCA\n-----END RSA PRIVATE KEY-----"
    When the gateway screens it
    Then the rule global.private_key fires
    And the text is redacted

  Scenario: global.private_key catches -----BEGIN PRIVATE KEY----- abc -----END PRIVATE...
    Given a tool result containing "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----"
    When the gateway screens it
    Then the rule global.private_key fires
    And the text is redacted

  Scenario: global.private_key leaves the private key lives in the vault alone
    Given a tool result containing "the private key lives in the vault"
    When the gateway screens it
    Then no rule fires

  Scenario: global.private_key leaves -----BEGIN CERTIFICATE----- alone
    Given a tool result containing "-----BEGIN CERTIFICATE-----"
    When the gateway screens it
    Then no rule fires

  # global.bearer_token -- BLOCKER
  # An Authorization header carried a token in clear text.

  Scenario: global.bearer_token catches Authorization: Bearer eyJhbGciOiJIUzI1NiJ9abcdef
    Given a tool result containing "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9abcdef"
    When the gateway screens it
    Then the rule global.bearer_token fires
    And the text is redacted

  Scenario: global.bearer_token catches authorization: basic dXNlcjpwYXNzd29yZA==
    Given a tool result containing "authorization: basic dXNlcjpwYXNzd29yZA=="
    When the gateway screens it
    Then the rule global.bearer_token fires
    And the text is redacted

  Scenario: global.bearer_token leaves Authorization header is required alone
    Given a tool result containing "Authorization header is required"
    When the gateway screens it
    Then no rule fires

  Scenario: global.bearer_token leaves authorization: Bearer alone
    Given a tool result containing "authorization: Bearer"
    When the gateway screens it
    Then no rule fires

  # global.aws_access_key -- BLOCKER
  # An AWS access key id appeared in a tool output.

  Scenario: global.aws_access_key catches aws_access_key_id = AKIAIOSFODNN7EXAMPLE
    Given a tool result containing "aws_access_key_id = AKIAIOSFODNN7EXAMPLE"
    When the gateway screens it
    Then the rule global.aws_access_key fires
    And the text is redacted

  Scenario: global.aws_access_key catches ASIAY34FZKBOKMUTVV7A
    Given a tool result containing "ASIAY34FZKBOKMUTVV7A"
    When the gateway screens it
    Then the rule global.aws_access_key fires
    And the text is redacted

  Scenario: global.aws_access_key leaves AKIA is the prefix for a long-lived key alone
    Given a tool result containing "AKIA is the prefix for a long-lived key"
    When the gateway screens it
    Then no rule fires

  Scenario: global.aws_access_key leaves akiaiosfodnn7example alone
    Given a tool result containing "akiaiosfodnn7example"
    When the gateway screens it
    Then no rule fires

  # global.private_ssh_url -- WARNING
  # A URL carrying inline credentials; rotate it rather than reuse it.

  Scenario: global.private_ssh_url catches git clone https://user:hunter2password@github.co...
    Given a tool result containing "git clone https://user:hunter2password@github.com/x/y"
    When the gateway screens it
    Then the rule global.private_ssh_url fires
    And the text is redacted

  Scenario: global.private_ssh_url catches ssh://deploy:s3cr3tpass@host/repo
    Given a tool result containing "ssh://deploy:s3cr3tpass@host/repo"
    When the gateway screens it
    Then the rule global.private_ssh_url fires
    And the text is redacted

  Scenario: global.private_ssh_url leaves https://github.com/x/y alone
    Given a tool result containing "https://github.com/x/y"
    When the gateway screens it
    Then no rule fires

  Scenario: global.private_ssh_url leaves mailto:someone@example.com alone
    Given a tool result containing "mailto:someone@example.com"
    When the gateway screens it
    Then no rule fires

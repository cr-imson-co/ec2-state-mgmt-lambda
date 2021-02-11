# ec2-state-mgmt-lambda

ec2-state-mgmt-lambda is an AWS Lambda developed to handle daily EC2 state management.

## invocation

lambda should be invoked by CloudWatch events; recommended invoke times are within several minutes of :00, :15, :30, and :45 every hour.

e.g. invoking at `XX:03`, `XX:18`, `XX:33`, `XX:48`, using an AWS CloudWatch cron expression of `3,18,33,48 * * * ? *`

## configuration

ec2-state-mgmt-lambda is configured via tags on ec2 instances themselves, and environment variables for general configuration.

### environment variables

* `STATE_MGMT_TIMEZONE` - a string, containing the name of the timezone the Lambda should use when handling all time-oriented logic for determining start and stop event qualifications.  See [pytz documentation](https://pypi.org/project/pytz/) for information on the timezone names.

### modern tags

* `{'ec2_start': 'XX:00'}` OR `{'ec2_start': 'XX:15'}` OR `{'ec2_start': 'XX:30'}` OR `{'ec2_start': 'XX:45'}` - used to enforce start time of ~XX:00, ~XX:15, ~XX:30, or ~XX:45, depending on when the lambda is run.
* `{'ec2_stop': 'XX:00'}` OR `{'ec2_stop': 'XX:15'}` OR `{'ec2_stop': 'XX:30'}` OR `{'ec2_stop': 'XX:45'}` - used to enforce stop time of ~XX:00, ~XX:15, ~XX:30, or ~XX:45, depending on when the lambda is run.
* `{'ec2_start_on_weekends': 'true'}` - used to force state management start events on weekends (Saturday and Sunday); stop events still occur in the event that systems were manually started.

## license

MIT license; see `./LICENSE`.

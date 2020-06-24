# ec2-state-mgmt-lambda

ec2-state-mgmt-lambda is an AWS Lambda developed to handle daily EC2 state management.

## invocation

lambda should be invoked by CloudWatch events; recommended invoke times are within several minutes of :00, and within several minutes of :30 every hour.

e.g. invoking at `XX:03` and `XX:33`, using an AWS CloudWatch cron expression of `3,33 * * * ? *`

## configuration

ec2-state-mgmt-lambda is configured via tags on ec2 instances themselves, and environment variables for general configuration.

### environment variables

* `STATE_MGMT_TIMEZONE` - a string, containing the name of the timezone the Lambda should use when handling all time-oriented logic for determining start and stop event qualifications.  See [pytz documentation](https://pypi.org/project/pytz/) for information on the timezone names.

### legacy tags

Please note that support for legacy tags is for backwards compatibility and every effort should be made to avoid them.

* `{'scheduled': 'true'}` - legacy tag, used to enforce hardcoded start time of ~XX:XX, and hardcoded stop time of ~XX:XX.
* `{'scheduled_on': 'true'}` - legacy tag, used to enforce a hardcoded start time of ~06:00.
* `{'scheduled_off': 'true'}` - legacy tag, used to enforce a hardcoded stop time of ~18:00.
* `{'auto_on': 'XX'}` - legacy tag, used to enforce a variable start time of ~XX:00, where XX is specified by the tag.
* `{'auto_off': 'XX'}` - legacy tag, used to enforce a variable stop time of ~XX:00, where XX is specified by the tag.

### modern tags

* `{'ec2_start': 'XX:00'}` OR `{'ec2_start': 'XX:30'}` - used to enforce start time of ~XX:00 or ~XX:30, depending on when the lambda is run.
* `{'ec2_stop': 'XX:00'}` OR `{'ec2_stop': 'XX:30'}` - used to enforce stop time of ~XX:00 or ~XX:30, depending on when the lambda is run.
* `{'ec2_quiet_weekends': 'true'}` - used to prevent state management start events on weekends (Saturday and Sunday); stop events still occur in the event that systems were manually started.

## license

MIT license; see `./LICENSE`.

#!/usr/bin/env python
'''
#
# cr.imson.co
#
# Automated state management service for EC2 instances
#
# @author Damian Bushong <katana@odios.us>
#
'''

# pylint: disable=C0116,C0301,C0411,W0511,W1202,R0911

from datetime import datetime
import pytz

from crimsoncore import LambdaCore

from aws_xray_sdk.core import patch_all
patch_all()

LAMBDA_NAME = 'ec2-state-mgmt'
LAMBDA = LambdaCore(LAMBDA_NAME)
LAMBDA.init_ec2()
LAMBDA.init_s3()
LAMBDA.init_sns()

# note: time should be specified in 24hr time and according to the configured STATE_MGMT_TIMEZONE
HARDCODED_START = '06:00'.split(':')[0]
HARDCODED_STOP = '18:00'.split(':')[0]

class RecoveredError(Exception): # pylint: disable=C0115
    pass

def tag_list_to_dict(tags):
    ''' Collapses the list of tags that AWS provides for EC2s down into a simple dict. '''
    return {t['Key']:t['Value'] for t in tags}

def _filter_start_instances(instance, current_hour, is_midhour_event, is_weekend):
    state = instance.state.get('Name')
    if state != 'stopped':
        LAMBDA.logger.debug(f'Instance {instance.id} is not stopped (status: {state}), ignoring')
        return False

    tags = tag_list_to_dict(instance.tags)

    # supports {'ec2_quiet_weekends' => 'true'}
    # notes:
    # - suppresses all start events during weekends if the ec2_quiet_weekends tag is set to "true"
    if 'ec2_quiet_weekends' in tags and tags['ec2_quiet_weekends'].lower() == 'true' and is_weekend:
        LAMBDA.logger.debug(f'Instance {instance.id} is tagged with "ec2_quiet_weekends" and it is a weekend, ignoring')
        return False

    # LEGACY TAG
    # supports {'scheduled' => 'true'}
    # notes:
    # - midhour events are not supported with this tag
    if 'scheduled' in tags and tags['scheduled'].lower() == 'true':
        LAMBDA.logger.debug(f'Instance {instance.id} is tagged with "scheduled" tag')
        return current_hour == HARDCODED_START and not is_midhour_event

    # LEGACY TAG
    # supports {'scheduled_on' => 'true'}
    # notes:
    # - midhour events are not supported with this tag
    if 'scheduled_on' in tags and tags['scheduled_on'].lower() == 'true':
        LAMBDA.logger.debug(f'Instance {instance.id} is tagged with "scheduled_on" tag')
        return current_hour == HARDCODED_START and not is_midhour_event

    # LEGACY TAG
    # supports {'auto_on' => 'XX'}
    # notes:
    # - midhour events are not supported with this tag
    if 'auto_on' in tags and tags['auto_on'].lower() != 'false':
        LAMBDA.logger.debug(f'Instance {instance.id} is tagged with "auto_on" tag')
        return tags['auto_on'] == current_hour and not is_midhour_event

    # supports {'ec2_start' => 'XX:00'} and {'ec2_start' => 'XX:30'}
    # notes:
    # - additional specificity in the ec2 tag is ignored! don't try to be cheeky and say XX:45.  it will not be supported.
    if 'ec2_start' in tags:
        LAMBDA.logger.debug(f'Instance {instance.id} is tagged with "ec2_start" tag')
        start_time = tags['ec2_start'].split(':')
        if current_hour == start_time[0]:
            if 0 < int(start_time[1]) < 30:
                LAMBDA.logger.warning(f'Invalid minute specifier for instance {instance.id} (specified :{start_time[1]}, assuming :00)')
                start_time[1] = '00'
            elif 30 < int(start_time[1]) < 60:
                LAMBDA.logger.warning(f'Invalid minute specifier for instance {instance.id} (specified :{start_time[1]}, assuming :30)')
                start_time[1] = '30'

            if not is_midhour_event and start_time[1] == '00' or is_midhour_event and start_time[1] == '30':
                return True

    # catchall; do not send any start events
    return False

def _filter_stop_instances(instance, current_hour, is_midhour_event):
    state = instance.state.get('Name')
    if state != 'running':
        LAMBDA.logger.debug(f'Instance {instance.id} is not running (status: {state}), ignoring')
        return False

    tags = tag_list_to_dict(instance.tags)

    # LEGACY TAG
    # supports {'scheduled' => 'true'}
    # notes:
    # - midhour events are not supported with this tag
    if 'scheduled' in tags and tags['scheduled'].lower() == 'true':
        LAMBDA.logger.debug(f'Instance {instance.id} is tagged with "scheduled" tag')
        return current_hour == HARDCODED_STOP and not is_midhour_event

    # LEGACY TAG
    # supports {'scheduled_off' => 'true'}
    # notes:
    # - midhour events are not supported with this tag
    if 'scheduled_off' in tags and tags['scheduled_off'].lower() == 'true':
        LAMBDA.logger.debug(f'Instance {instance.id} is tagged with "scheduled_off" tag')
        return current_hour == HARDCODED_STOP and not is_midhour_event

    # LEGACY TAG
    # supports {'auto_off' => 'XX'}
    # notes:
    # - midhour events are not supported with this tag
    if 'auto_off' in tags and tags['auto_off'].lower() != 'false':
        LAMBDA.logger.debug(f'Instance {instance.id} is tagged with "auto_off" tag')
        return tags['auto_off'] == current_hour and not is_midhour_event

    # supports {'ec2_stop' => 'XX:00'} and {'ec2_stop' => 'XX:30'}
    # notes:
    # - additional specificity in the ec2 tag is ignored! don't try to be cheeky and say XX:45.  it will not be supported.
    if 'ec2_stop' in tags:
        LAMBDA.logger.debug(f'Instance {instance.id} is tagged with "ec2_stop" tag')
        stop_time = tags['ec2_stop'].split(':')
        if current_hour == stop_time[0]:
            if 0 < int(stop_time[1]) < 30:
                LAMBDA.logger.warning(f'Invalid minute specifier for instance {instance.id} (specified :{stop_time[1]}, assuming :00)')
                stop_time[1] = '00'
            elif 30 < int(stop_time[1]) < 60:
                LAMBDA.logger.warning(f'Invalid minute specifier for instance {instance.id} (specified :{stop_time[1]}, assuming :30)')
                stop_time[1] = '30'

            if not is_midhour_event and stop_time[1] == '00' or is_midhour_event and stop_time[1] == '30':
                return True

    # catchall; do not send any stop events
    return False

def filter_start_instances(instance, current_hour, is_midhour_event, is_weekend):
    ''' Tiny wrapper around the filter_start_instances function to shim in some extra logging. '''
    result = _filter_start_instances(instance, current_hour, is_midhour_event, is_weekend)

    if result:
        LAMBDA.logger.debug(f'Instance {instance.id} identified as qualifying for sending start event')
    else:
        LAMBDA.logger.debug(f'Instance {instance.id} does not qualify for start event, ignoring')

    return result

def filter_stop_instances(instance, current_hour, is_midhour_event):
    ''' Tiny wrapper around the filter_stop_instances function to shim in some extra logging. '''
    result = _filter_stop_instances(instance, current_hour, is_midhour_event)

    if result:
        LAMBDA.logger.debug(f'Instance {instance.id} identified as qualifying for sending stop event')
    else:
        LAMBDA.logger.debug(f'Instance {instance.id} does not qualify for stop event, ignoring')

    return result

def lambda_handler(event, context):
    try:
        timezone = pytz.timezone(LAMBDA.config.val('STATE_MGMT_TIMEZONE', default_override='UTC'))

        now = datetime.now(timezone)
        current_hour, current_minute = now.strftime('%H:%M').split(':')
        is_weekend = now.weekday() in [5, 6] # 5-6 are Saturday, Sunday ordinally
        is_midhour_event = (30 <= int(current_minute) <= 59)

        LAMBDA.logger.debug(f'current_hour: {current_hour}')
        LAMBDA.logger.debug(f'current_minute: {current_minute}')
        LAMBDA.logger.debug(f'is_weekend: {is_weekend}')
        LAMBDA.logger.debug(f'is_midhour_event: {is_midhour_event}')

        # start_filters = []
        # if current_hour == HARDCODED_START and
        start_instances = []
        stop_instances = []

        # due to us needing to interact with both started and stopped EC2 instances with
        #   filtering more complex than AWS's APIs can support, it's more efficient to just
        #   get a full instance list and roll with it up front.
        #
        # also, pylint apparently doesn't understand that LAMBDA.ec2 is lazy-loaded...
        instances = list(LAMBDA.ec2.instances.all()) # pylint: disable=E1101

        LAMBDA.logger.debug(f'Retrieved {len(instances)} instances total')

        start_instances = list(filter(lambda instance_list: filter_start_instances(instance_list, current_hour, is_midhour_event, is_weekend), instances[:]))
        stop_instances = list(filter(lambda instance_list: filter_stop_instances(instance_list, current_hour, is_midhour_event), instances[:]))

        LAMBDA.logger.debug(f'Filtered instances to start down to {len(start_instances)} instances total')
        LAMBDA.logger.debug(f'Filtered instances to stop down to {len(stop_instances)} instances total')

        failure_count = 0
        if (len(start_instances)) > 0:
            for instance in start_instances:
                LAMBDA.logger.info(f'Starting instance {instance.id}')

                try:
                    instance.start()
                except Exception as ex: # pylint: disable=W0703
                    LAMBDA.logger.error(f'Failed to start instance {instance.id}', exc_info=ex)
                    failure_count += 1
        else:
            LAMBDA.logger.info('No instances to start.')

        if (len(stop_instances)) > 0:
            for instance in stop_instances:
                LAMBDA.logger.info(f'Stopping instance {instance.id}')

                try:
                    instance.stop()
                except Exception as ex: # pylint: disable=W0703
                    LAMBDA.logger.error(f'Failed to start instance {instance.id}', exc_info=ex)
                    failure_count += 1
        else:
            LAMBDA.logger.info('No instances to stop.')

        if failure_count:
            raise RecoveredError(f'{failure_count} instance control failures occurred')
    except Exception as ex:
        LAMBDA.logger.error('Fatal error during script runtime', exc_info=ex)
        LAMBDA.send_notification('error', f'{LAMBDA_NAME} lambda error notification; reference logstream {LAMBDA.config.get_log_stream()}')

        raise

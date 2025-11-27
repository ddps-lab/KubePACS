import json
import boto3
import csv
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

# Constants
PROFILE_NAME = "ddpslab"
REGION_NAME = "us-east-1"
START_EVENT_NAMES = ['RunInstances', 'StartInstances']
STOP_EVENT_NAMES = ['StopInstances', 'TerminateInstances', 'BidEvictedEvent']
DAYS_TO_LOOK_BACK = 2
START_EVENTS_JSON_FILE = 'start_events_filtered.json'
STOP_EVENTS_JSON_FILE = 'stop_events_filtered.json'
INSTANCE_USAGE_CSV_FILE = 'instance_usage_data_filtered.csv'


def get_cloudtrail_events(
    client: Any,
    event_names: List[str],
    start_time: datetime,
    end_time: datetime
) -> List[Dict[str, Any]]:
    """Fetches CloudTrail events for a list of event names within a time range."""
    all_events = []
    for event_name in event_names:
        print(f"Fetching events for {event_name}...")
        events = []
        next_token = None
        page_count = 0
        while True:
            page_count += 1
            print(f"  Fetching page {page_count} for {event_name}...")
            params = {
                'LookupAttributes': [{
                    "AttributeKey": 'EventName',
                    "AttributeValue": event_name
                }],
                'StartTime': start_time,
                'EndTime': end_time,
                'MaxResults': 50
            }
            if next_token:
                params['NextToken'] = next_token

            try:
                response = client.lookup_events(**params)
                fetched_events = response.get('Events', [])
                print(f"  Fetched {len(fetched_events)} events on page {page_count} for {event_name}.")
                events.extend(fetched_events)
                next_token = response.get('NextToken')
                if not next_token:
                    print(f"  No more pages for {event_name}.")
                    break
            except client.exceptions.ClientError as e:
                if "Rate exceeded" in str(e):
                    print(f"WARN: Rate limit possibly exceeded for {event_name}. Retrying might be needed.")
                else:
                    print(f"ERROR: Boto3 ClientError fetching events for {event_name}: {e}")
                break
            except Exception as e:
                print(f"ERROR: Unexpected error fetching events for {event_name}: {e}")
                break
        print(f"Finished fetching for {event_name}. Total events found: {len(events)}")
        all_events.extend(events)
    print(f"Total events fetched across all types: {len(all_events)}")
    return all_events


def save_events_to_json(events: List[Dict[str, Any]], filename: str) -> None:
    """Saves a list of events to a JSON file."""
    try:
        serializable_events = []
        for event in events:
            event_copy = event.copy()
            # Convert datetime objects to ISO format strings
            for key, value in event_copy.items():
                if isinstance(value, datetime):
                    event_copy[key] = value.isoformat()
            serializable_events.append(event_copy)

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(serializable_events, f, ensure_ascii=False, indent=4)
        print(f"Event data saved to {filename}.")
    except Exception as e:
        print(f"Error saving events to JSON file {filename}: {e}")


def parse_datetime(time_str: Any) -> Optional[datetime]:
    """Safely parses a datetime string or object."""
    if isinstance(time_str, datetime):
        if time_str.tzinfo is None or time_str.tzinfo.utcoffset(time_str) is None:
            return time_str.replace(tzinfo=timezone.utc)
        return time_str.astimezone(timezone.utc)
    if isinstance(time_str, str):
        try:
            if time_str.endswith('Z'):
                if '.' in time_str:
                    try:
                        dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                    except ValueError:
                        dt = datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
                else:
                    dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
            else:
                dt = datetime.fromisoformat(time_str)

            if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)

        except ValueError as e:
            print(f"Error parsing datetime string '{time_str}': {e}")
            return None
    return None


def process_start_events(
    start_events: List[Dict[str, Any]],
    instance_data: Dict[str, Dict[str, Any]],
    target_instance_ids: List[str]
) -> None:
    """Processes start events to populate instance data ONLY for target IDs."""
    print(f"\nProcessing {len(start_events)} start events...")
    target_ids_set = set(target_instance_ids)
    processed_count = 0
    updated_count = 0

    for event in start_events:
        processed_count += 1
        if processed_count % 100 == 0:
            print(f"  Processed {processed_count}/{len(start_events)} start events...")
        try:
            event_details = json.loads(event.get('CloudTrailEvent', '{}'))
            event_time = parse_datetime(event.get('EventTime'))
            if not event_time:
                continue

            response_elements = event_details.get('responseElements')
            instances = []
            if response_elements:
                instances_set = response_elements.get('instancesSet')
                if instances_set:
                    instances = instances_set.get('items', [])

            for instance in instances:
                instance_id = instance.get('instanceId')
                instance_type = instance.get('instanceType')
                placement = instance.get('placement', {})
                availability_zone = placement.get('availabilityZone')

                if instance_id and instance_id in target_ids_set:
                    updated = False
                    current_start = instance_data[instance_id].get('start_time')
                    if not current_start or event_time > current_start:
                        instance_data[instance_id]['start_time'] = event_time
                        updated = True

                    if instance_type and not instance_data[instance_id].get('instance_type'):
                        instance_data[instance_id]['instance_type'] = instance_type
                        updated = True
                    if availability_zone and not instance_data[instance_id].get('availability_zone'):
                        instance_data[instance_id]['availability_zone'] = availability_zone
                        updated = True

                    if updated:
                        updated_count += 1

        except json.JSONDecodeError as e:
            print(f"ERROR: JSONDecodeError in start event {event.get('EventId')}: {e}")
        except Exception as e:
            import traceback
            print(f"ERROR: Unexpected error processing start event {event.get('EventId')}: {e}")
    print(f"Finished processing start events. Updated info for {updated_count} target instance starts.")


def extract_instance_ids_from_stop_event(event_details: Dict[str, Any]) -> List[str]:
    """Extracts instance IDs from various stop event structures."""
    instance_ids = set()

    response_elements = event_details.get('responseElements')
    request_parameters = event_details.get('requestParameters')
    event_name = event_details.get('eventName')

    if event_name == 'BidEvictedEvent':
        service_details = event_details.get('serviceEventDetails', {})
        instance_id_set = service_details.get("instanceIdSet")
        if instance_id_set and isinstance(instance_id_set, list):
            instance_ids.update(inst_id for inst_id in instance_id_set if inst_id)
        elif instance_id_set and isinstance(instance_id_set, dict) and 'items' in instance_id_set:
            instance_ids.update(item.get('instanceId') for item in instance_id_set['items'] if item.get('instanceId'))

    elif event_name == 'TerminateInstances':
        if request_parameters:
            instances = request_parameters.get('instancesSet', {}).get('items', [])
            instance_ids.update(inst.get('instanceId') for inst in instances if inst.get('instanceId'))
            single_id = request_parameters.get('instanceId')
            if single_id:
                instance_ids.add(single_id)
        if response_elements:
            instances = response_elements.get('instancesSet', {}).get('items', [])
            instance_ids.update(inst.get('instanceId') for inst in instances if inst.get('instanceId'))

    elif event_name == 'StopInstances':
        if response_elements:
            instances = response_elements.get('instancesSet', {}).get('items', [])
            instance_ids.update(inst.get('instanceId') for inst in instances if inst.get('instanceId'))
        elif request_parameters:
            instances = request_parameters.get('instancesSet', {}).get('items', [])
            instance_ids.update(inst.get('instanceId') for inst in instances if inst.get('instanceId'))
            single_id = request_parameters.get('instanceId')
            if single_id:
                instance_ids.add(single_id)

    return list(instance_ids)


def process_stop_events(
    stop_events: List[Dict[str, Any]],
    instance_data: Dict[str, Dict[str, Any]],
    target_instance_ids: List[str]
) -> None:
    """Processes stop events to update instance stop times ONLY for target IDs."""
    print(f"\nProcessing {len(stop_events)} stop events...")
    target_ids_set = set(target_instance_ids)
    processed_count = 0
    updated_count = 0

    for event in stop_events:
        processed_count += 1
        if processed_count % 100 == 0:
            print(f"  Processed {processed_count}/{len(stop_events)} stop events...")
        try:
            event_details = json.loads(event.get('CloudTrailEvent', '{}'))
            event_time = parse_datetime(event.get('EventTime'))
            if not event_time:
                continue

            instance_ids = extract_instance_ids_from_stop_event(event_details)

            for instance_id in instance_ids:
                if instance_id and instance_id in target_ids_set and instance_id in instance_data:
                    current_stop = instance_data[instance_id].get('stop_time')
                    if not current_stop or event_time > current_stop:
                        instance_data[instance_id]['stop_time'] = event_time
                        updated_count += 1

        except json.JSONDecodeError as e:
            print(f"ERROR: JSONDecodeError in stop event {event.get('EventId')}: {e}")
        except Exception as e:
            import traceback
            print(f"ERROR: Unexpected error processing stop event {event.get('EventId')}: {e}")
    print(f"Finished processing stop events. Updated info for {updated_count} target instance stops.")


def save_instance_data_to_csv(
    instance_data: Dict[str, Dict[str, Any]],
    filename: str
) -> None:
    """Saves the processed instance data to a CSV file."""
    print(f"\nSaving instance data for {len(instance_data)} instances to {filename}...")
    saved_count = 0
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['instanceID', 'instanceType', 'AZ', 'startTime', 'stopTime', 'status', 'durationSec'])

            for instance_id in sorted(instance_data.keys()):
                data = instance_data[instance_id]
                start_time = data.get('start_time')
                stop_time = data.get('stop_time')

                start_time_aware = parse_datetime(start_time) if start_time else None
                stop_time_aware = parse_datetime(stop_time) if stop_time else None

                start_time_str = start_time_aware.isoformat() if start_time_aware else None
                stop_time_str = stop_time_aware.isoformat() if stop_time_aware else None

                status = 'running'
                duration_seconds = None

                if start_time_aware and stop_time_aware:
                    if stop_time_aware >= start_time_aware:
                        duration = stop_time_aware - start_time_aware
                        duration_seconds = duration.total_seconds()
                        status = 'stopped'
                    else:
                        status = 'stopped (invalid duration)'
                        print(f"WARN: Instance {instance_id} has stop time ({stop_time_str}) before start time ({start_time_str}).")
                elif start_time_aware and not stop_time_aware:
                    status = 'running (or stopped outside window)'
                elif not start_time_aware:
                    status = 'unknown (no start event found)'

                writer.writerow([
                    instance_id,
                    data.get('instance_type', 'N/A'),
                    data.get('availability_zone', 'N/A'),
                    start_time_str if start_time_str else '',
                    stop_time_str if stop_time_str else '',
                    status,
                    duration_seconds if duration_seconds is not None else ''
                ])
                saved_count += 1
        print(f"Successfully saved data for {saved_count} instances to {filename}.")
    except Exception as e:
        print(f"Error saving instance data to CSV file {filename}: {e}")


if __name__ == "__main__":
    TARGET_INSTANCE_IDS =['i-0555a84a0dd27adb8', 'i-0783a17b2a88112c8', 'i-0a827475301496ca9', 'i-0e003dbc67d82c398', 'i-0e9395a59be011c20', 'i-0f0a5b23e2f2cf814']

    print(f"Targeting {len(TARGET_INSTANCE_IDS)} specific instance IDs.")
    if not TARGET_INSTANCE_IDS or "i-xxxxxxxxxxxxxxxxx" in TARGET_INSTANCE_IDS:
        print("Error: TARGET_INSTANCE_IDS list is empty or contains placeholder IDs. Please provide valid instance IDs to analyze.")
        exit(1)

    try:
        session = boto3.Session(profile_name=PROFILE_NAME)
        cloudtrail_client = session.client('cloudtrail', region_name=REGION_NAME)
    except Exception as e:
        print(f"Error creating Boto3 session/client: {e}")
        exit(1)

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=DAYS_TO_LOOK_BACK)

    print(f"\nFetching CloudTrail events from {start_time.isoformat()} to {end_time.isoformat()}")

    start_events = get_cloudtrail_events(cloudtrail_client, START_EVENT_NAMES, start_time, end_time)
    stop_events = get_cloudtrail_events(cloudtrail_client, STOP_EVENT_NAMES, start_time, end_time)

    instance_data: Dict[str, Dict[str, Any]] = {
        instance_id: {
            'start_time': None,
            'stop_time': None,
            'instance_type': None,
            'availability_zone': None
        } for instance_id in TARGET_INSTANCE_IDS
    }

    process_start_events(start_events, instance_data, TARGET_INSTANCE_IDS)
    process_stop_events(stop_events, instance_data, TARGET_INSTANCE_IDS)

    save_instance_data_to_csv(instance_data, INSTANCE_USAGE_CSV_FILE)

    print(f"\nAnalysis complete for {len(TARGET_INSTANCE_IDS)} requested instances.")

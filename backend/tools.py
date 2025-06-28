import os
import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import BaseModel, Field
import json

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_calendar_service():
    """Shows basic usage of the Google Calendar API.
    Prints the start and name of the next 10 events on the user's calendar.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    
    return build('calendar', 'v3', credentials=creds)

class CheckAvailabilityInput(BaseModel):
    start_time: str = Field(description="Start time of the proposed event in ISO 8601 format (e.g., '2025-06-28T09:00:00+05:30').")
    end_time: str = Field(description="End time of the proposed event in ISO 8601 format (e.g., '2025-06-28T10:00:00+05:30').")

def check_calendar_availability(start_time: str, end_time: str):
    """Checks the user's primary calendar for availability within a given time range.
    Returns a list of busy time slots.
    """
    try:
        service = get_calendar_service()
        
        # We need to get the timezone for the user's calendar.
        calendar_id = 'primary'
        calendar_info = service.calendars().get(calendarId=calendar_id).execute()
        timezone = calendar_info.get('timeZone', 'UTC')
        
        # Convert to datetime objects
        start = datetime.datetime.fromisoformat(start_time)
        end = datetime.datetime.fromisoformat(end_time)
        
        body = {
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "timeZone": timezone,
            "items": [{"id": calendar_id}]
        }
        
        free_busy_query = service.freebusy().query(body=body).execute()
        
        busy_slots = free_busy_query['calendars'][calendar_id]['busy']
        
        if not busy_slots:
            return "The calendar is free during this time."
        else:
            busy_list = []
            for slot in busy_slots:
                busy_list.append(f"From {slot['start']} to {slot['end']}")
            return f"The calendar is busy during the following times: {', '.join(busy_list)}. Please suggest a different time."

    except HttpError as error:
        return f"An error occurred while checking availability: {error}"

class CreateEventInput(BaseModel):
    summary: str = Field(description="Summary of the event.")
    start_time: str = Field(description="Start time of the event in ISO 8601 format (e.g., '2025-06-28T09:00:00+05:30').")
    end_time: str = Field(description="End time of the event in ISO 8601 format (e.g., '2025-06-28T10:00:00+05:30').")
    description: str = Field(description="Description of the event.")
    attendees: list[str] = Field(description="List of email addresses of attendees. Optional.")

def create_google_calendar_event(summary: str, start_time: str, end_time: str, description: str = "", attendees: list[str] = None):
    """Creates a new event on the user's primary Google Calendar."""
    try:
        service = get_calendar_service()

        event = {
            'summary': summary,
            'description': description,
            'start': {
                'dateTime': start_time,
                'timeZone': 'Asia/Kolkata', # Default to IST, can be dynamic
            },
            'end': {
                'dateTime': end_time,
                'timeZone': 'Asia/Kolkata',
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60},
                    {'method': 'popup', 'minutes': 10},
                ],
            },
        }

        if attendees:
            event['attendees'] = [{'email': email} for email in attendees]

        event = service.events().insert(calendarId='primary', body=event).execute()
        return f"Event created: {event.get('htmlLink')}"

    except HttpError as error:
        return f"An error occurred while creating the event: {error}"

# Pydantic models for tool schemas (LangGraph uses this for tool calling)
check_availability_tool_schema = {
    "name": "check_calendar_availability",
    "description": "Checks for busy time slots on the user's primary Google Calendar within a specified time range.",
    "parameters": CheckAvailabilityInput.model_json_schema()
}

create_event_tool_schema = {
    "name": "create_google_calendar_event",
    "description": "Creates a new event on the user's primary Google Calendar with the given details.",
    "parameters": CreateEventInput.model_json_schema()
}

# This is a helper function to get the current date and time
def get_current_datetime():
    """Returns the current date and time in ISO 8601 format."""
    return datetime.datetime.now().isoformat()
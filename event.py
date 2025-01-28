import json
from CDP_Chatbot.time_convert import convert_to_12hr_format
import datetime
from datetime import datetime

#When user provides only day                we send list event with time 
def get_events_day(day):
    with open('data.json', 'r') as file:
        tournament = json.load(file)        #Get data 
        for t in tournament:                #Consider each entry day wise
            if t['day'] == day:             #Day Match
                return [f"{event['event']} at {event['time']}" for event in t['events']]  #Create a list of formatted event strings
        return [f"No events found for day {day}."]   #Return a fallback message if no events found for the given day

#When user provides only event              we send them time and day 
def get_events_event(event):
    with open('data.json', 'r') as file:
        data = json.load(file)
        results = []
        for day_data in data:
            day = day_data["day"]
            for event_data in day_data["events"]:       #fatching all events for a day
                if event.lower() in event_data["event"].lower():    #match events
                    event_times = event_data["time"]
                    s=""
                    if len(event_times)<=1:
                        time="".join(event_times)
                        s=f'{event_data["event"]} will be at {time} on Day {day}'
                        print(s)
                    elif len(event_times)<=2:
                        s=f'{event_data["event"]} will be from {event_times[0]} to {event_times[1]} on Day {day}'                    
                    results.append(s)
                    
    return results


def get_events_day_time(day, user_time):
    # Convert the provided time to 12-hour format (e.g., 3:00 pm)
    user_time_12hr = convert_to_12hr_format(user_time)
    events_list = []  # List to store matching events
    print("funtion called dear ")
    with open('data.json', 'r') as file:
        data = json.load(file)
        for day_data in data:
            if day_data["day"] == day:
                print("Day matched")
                for event_data in day_data["events"]:
                    event_times = event_data["time"]
                    event_name = event_data["event"]
                    
                    # Check if the user's time matches one of the event times
                    for time in event_times:
                        event_time_12hr = time.lower()  # Convert event time to lowercase
                        if user_time_12hr == event_time_12hr:
                            if len(event_times)<2:
                                events_list.append(f'{event_name} will be at {user_time_12hr[0]} to {user_time_12hr[1]} ')
                            else:
                                events_list.append(f'{event_name} will be at {user_time_12hr} ')
                    
                    # Check if the user's time is between the first and last event times (range)
                    try:
                        # Convert event times and user's time to datetime objects for comparison
                        event_time_start = datetime.strptime(event_times[0], '%I:%M %p')
                        event_time_end =datetime.strptime(event_times[-1], '%I:%M %p')
                        user_time_obj = datetime.strptime(user_time_12hr, '%I:%M %p')
                        
                        if event_time_start <= user_time_obj <= event_time_end:
                            events_list.append(f'{event_name} is happening between {event_times[0]} and {event_times[-1]} ')
                    except Exception as e:
                        # Handle any errors during time conversion (e.g., when only one time is provided)
                        print(e)

    if events_list:
        return events_list
    else:
        return ["No event found for the given day and time."]
    


def get_time_for_event_on_day(day, event_name):
    # Load the JSON data
    with open('data.json', 'r') as file:
        data = json.load(file)
    
    # Initialize an empty list to store the results
    responses = []
    
    # Iterate through the days and events to find the event and its associated times
    for day_data in data:
        if day_data["day"] == day:  # Match the day
            for event_data in day_data["events"]:
                # Check if the event matches (case insensitive)
                if event_name.lower() in event_data["event"].lower():
                    # If event is found, format the time range into a response
                    event_times = event_data["time"]
                    print("lengt of list")
                    print(len(event_times))

                    if len(event_times)<=2:
                        responses.append(f'{event_name} will be from {event_times[0]} to {event_times[1]} ')
                    else:
                        responses.append(f'{event_name} will be at vairous time')
                        x=[]
                        for i in range(len(event_times)):
                            x.append(event_times[i])
                            time=" , ".join(x)
                        responses.append(time)
                        print(responses)
                        print(type(responses))
    
    # If no events are found, return the custom message in a list
    if not responses:
        responses.append("We don't have any updates on this")
    
    return responses

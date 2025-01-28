from datetime import datetime

def convert_to_12hr_format(iso_time):
    try:
        # Parse the ISO 8601 time string (e.g., "2025-01-22T15:00:00+05:30")
        time_obj = datetime.fromisoformat(iso_time)  # Parse the ISO format
        formatted_time = time_obj.strftime('%I:%M %p')  # Convert to 12-hour format (hh:mm am/pm)
        print(formatted_time.strip().lower())
        return formatted_time.strip().lower()  # Return the time in lowercase for case-insensitive comparison
    
    except ValueError:
        return None  # Invalid time format
    
# Test the function with a valid ISO time string


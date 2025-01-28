from flask import Flask,request,jsonify
from event import get_events_day
from event import get_events_event
from event import get_events_day_time
from datetime import datetime
from event import get_time_for_event_on_day
from helper_function import formate_dialogflow_response
from question import similar_quizz
from helper_function import quick_reply
common_events=[
     "breakfast",
     "lunch",
     "dinner",
     "game times"
]           
app = Flask(__name__) 

@app.route('/')
def handle_home():
    return 'OK', 200

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    data = request.json
    intent_name = data.get("queryResult", {}).get("intent", {}).get("displayName", None)
    if intent_name=="TournamentInraties":
        parameters = data.get("queryResult", {}).get("parameters", {})
        day = parameters.get("day", None)
        events = parameters.get("event", None)  # Using None as the default if the key is missing
        time = parameters.get("time", None)
        event="".join(events)
        x = len(time)

        #Case 1
        #Nothing given
        if day == None and event == None and time == None:
            return jsonify(formate_dialogflow_response(["Could you please mention Day or event so that I can answer you"]))

        #case 2
        #Only day is given
        elif day!=None and time=="" and event =="":
                list_of_event=get_events_day(day)       
                result = " ".join(list_of_event)
                return jsonify(formate_dialogflow_response(["Dear User,We found that ",result]))
    
        #case 3
        #only event is givenN 
        elif event!=None and day=="" and time=="":
            if event in common_events:
                 return jsonify(formate_dialogflow_response(["Dear User,We found that ",event," is on many days kindly mention day"]))
            result=get_events_event(event)      
            if result:
                for res in result:
                    return jsonify(formate_dialogflow_response([res]))

        #case 4       
        #Day and time given
        elif x>0 and day!=None and event!=None:
            result=get_events_day_time(day,time)
            if result:
                    return jsonify(formate_dialogflow_response(result))

        #case 5
        # Day and event are given        
        elif day!=None and time=="" and events != None:
            result=get_time_for_event_on_day(day,event)
            if result:
                    return jsonify(formate_dialogflow_response(result))

        #If none of the above conditions are met but still bot 
        #Defines it as "tournament event" intent. Thus we Need to provide some response.
        else:
            return jsonify(formate_dialogflow_response(["Dear User, How May I help you "]))
    elif intent_name =="unknown":
        query_text = data["queryResult"]["queryText"]
        same_questions=similar_quizz(query_text)
        if same_questions:
            return jsonify(quick_reply(same_questions))
        else:
             return jsonify(formate_dialogflow_response(["Could you please repeat your question"]))
    else:
         return jsonify(formate_dialogflow_response(["Could you please repeat your question precisly"]))
    

if __name__ == '__main__':
    app.run(debug=True)
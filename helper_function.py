def formate_dialogflow_response(messages : list[str]):
    response_data={
        "fulfillmentMessages": []
        }
    for m in messages:
        response_data["fulfillmentMessages"].append({
            "text": {
                                             "text": [m]
                                            }

        })
    return response_data


def quick_reply(statements):
    # Quick Replies as buttons
    options = [{"text": statement} for statement in statements]
    response = {
        "fulfillmentMessages": [
            {
                "text": {
                    "text": ["Please select one of the following options:"]
                }
            },
            {
                "payload": {
                    "richContent": [
                        [
                            {
                                "type": "chips",
                                "options": options
                            }
                        ]
                    ]
                }
            }
        ]
    }
    return response
import json
from channels.generic.websocket import AsyncWebsocketConsumer

class SubmissionConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # 1. Get the submission ID from the URL (ws://.../submission/123/)
        self.submission_id = self.scope['url_route']['kwargs']['submission_id']
        
        # 2. Create a group specifically for this submission
        # This matches the group name used in executor_service.py
        self.room_group_name = f'submission_{self.submission_id}'

        # 3. Join the group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave the group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # This method receives the message from the Executor/Kafka
    async def submission_update(self, event):
        # 4. Forward the message to the Frontend
        # We extract 'message' because that's how we structured it in the Executor
        message = event['message']

        await self.send(text_data=json.dumps(message))
from __future__ import annotations

from typing import Callable

from botbuilder.core import ActivityHandler, TurnContext, UserState, ConversationState
from botbuilder.dialogs import Dialog, DialogExtensions


class RegistrationBot(ActivityHandler):
    def __init__(
        self,
        conversation_state: ConversationState,
        user_state: UserState,
        dialog: Dialog,
    ) -> None:
        if conversation_state is None:
            raise TypeError("[RegistrationBot]: Exception: conversation_state is required")
        if user_state is None:
            raise TypeError("[RegistrationBot]: Exception: user_state is required")
        if dialog is None:
            raise TypeError("[RegistrationBot]: Exception: dialog is required")

        self.conversation_state = conversation_state
        self.user_state = user_state
        self.dialog = dialog

    async def on_turn(self, turn_context: TurnContext) -> None:
        await super().on_turn(turn_context)

        # Save any state changes that might have occurred during the turn.
        await self.conversation_state.save_changes(turn_context)
        await self.user_state.save_changes(turn_context)

    async def on_message_activity(self, turn_context: TurnContext) -> None:
        await DialogExtensions.run_dialog(
            self.dialog,
            turn_context,
            self.conversation_state.create_property("DialogState"),
        )

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
        if turn_context.activity.text:
            text = turn_context.activity.text.lower().strip()
            if text in ["neustart", "restart", "zurücksetzen"]:
                await self.conversation_state.delete(turn_context)
                await self.user_state.delete(turn_context)
                await turn_context.send_activity("Alles klar, wir fangen von vorne an.")
            elif text in ["status", "info", "bereits gesammelt", "was weißt du schon", "zusammenfassung", "stand", "informationen", "was hast du"]:
                user_profile_accessor = self.user_state.create_property("UserProfile")
                from .models import UserProfile
                user_profile = await user_profile_accessor.get(turn_context, UserProfile)
                
                collected = []
                if user_profile.first_name or user_profile.last_name:
                    collected.append(f"Name: {user_profile.first_name or ''} {user_profile.last_name or ''}".strip())
                if user_profile.birthdate:
                    collected.append(f"Geburtsdatum: {user_profile.birthdate}")
                
                addr_parts = []
                if user_profile.street:
                    addr_parts.append(f"{user_profile.street} {user_profile.house_number or ''}".strip())
                if user_profile.postal_code or user_profile.city:
                    addr_parts.append(f"{user_profile.postal_code or ''} {user_profile.city or ''}".strip())
                if user_profile.country:
                    addr_parts.append(user_profile.country)
                if addr_parts:
                    collected.append(f"Adresse: {', '.join(addr_parts)}")
                    
                if user_profile.email:
                    collected.append(f"E-Mail: {user_profile.email}")
                if user_profile.phone:
                    collected.append(f"Telefon: {user_profile.phone}")
                    
                if collected:
                    details = "\n- ".join(collected)
                    msg = f"Ich habe bisher folgende Daten gesammelt:\n- {details}"
                else:
                    msg = "Ich habe bisher noch keine Daten gesammelt."
                
                await turn_context.send_activity(msg)
                
        await DialogExtensions.run_dialog(
            self.dialog,
            turn_context,
            self.conversation_state.create_property("DialogState"),
        )

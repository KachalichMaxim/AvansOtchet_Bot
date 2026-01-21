"""Finite State Machine for operation flow."""
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass, field


class State(Enum):
    """FSM states."""
    IDLE = "IDLE"
    SELECT_OPERATION_TYPE = "SELECT_OPERATION_TYPE"
    SELECT_DATE = "SELECT_DATE"
    INPUT_AMOUNT = "INPUT_AMOUNT"
    SELECT_CATEGORY = "SELECT_CATEGORY"
    SELECT_TYPE = "SELECT_TYPE"
    SELECT_RENTAL_ADDRESS = "SELECT_RENTAL_ADDRESS"
    SELECT_RENTAL_MM = "SELECT_RENTAL_MM"
    INPUT_RENTAL_AMOUNT = "INPUT_RENTAL_AMOUNT"
    INPUT_DESCRIPTION = "INPUT_DESCRIPTION"
    CONFIRM = "CONFIRM"
    SAVE = "SAVE"


@dataclass
class OperationContext:
    """Context for storing operation data during FSM flow."""
    direction: Optional[str] = None  # "IN" or "OUT"
    date: Optional[str] = None  # dd.mm.yyyy
    amount: Optional[float] = None
    category: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None
    rental_address: Optional[str] = None  # For rental operations
    rental_mm: Optional[str] = None  # For rental operations


class FSM:
    """Finite State Machine for managing operation flow."""
    
    def __init__(self):
        """Initialize FSM with user state storage."""
        self.user_states: Dict[int, State] = {}  # user_id -> state
        self.user_contexts: Dict[int, OperationContext] = {}  # user_id -> context
    
    def get_state(self, user_id: int) -> State:
        """Get current state for user."""
        return self.user_states.get(user_id, State.IDLE)
    
    def set_state(self, user_id: int, state: State):
        """Set state for user."""
        self.user_states[user_id] = state
    
    def get_context(self, user_id: int) -> OperationContext:
        """Get operation context for user."""
        if user_id not in self.user_contexts:
            self.user_contexts[user_id] = OperationContext()
        return self.user_contexts[user_id]
    
    def reset(self, user_id: int):
        """Reset user state and context."""
        self.user_states[user_id] = State.IDLE
        self.user_contexts[user_id] = OperationContext()
    
    def start_operation(self, user_id: int):
        """Start new operation flow."""
        self.set_state(user_id, State.SELECT_OPERATION_TYPE)
        self.user_contexts[user_id] = OperationContext()
    
    def set_direction(self, user_id: int, direction: str):
        """Set operation direction and move to next state."""
        context = self.get_context(user_id)
        context.direction = direction
        self.set_state(user_id, State.SELECT_DATE)
    
    def set_date(self, user_id: int, date: str):
        """Set operation date and move to next state."""
        context = self.get_context(user_id)
        context.date = date
        self.set_state(user_id, State.INPUT_AMOUNT)
    
    def set_amount(self, user_id: int, amount: float):
        """Set operation amount and move to next state."""
        context = self.get_context(user_id)
        context.amount = amount
        self.set_state(user_id, State.SELECT_CATEGORY)
    
    def set_category(self, user_id: int, category: str):
        """Set operation category and move to next state."""
        context = self.get_context(user_id)
        context.category = category
        # If category is "Доходы от аренды", go to address selection instead of type
        if category == "Доходы от аренды":
            self.set_state(user_id, State.SELECT_RENTAL_ADDRESS)
        else:
            self.set_state(user_id, State.SELECT_TYPE)
    
    def set_type(self, user_id: int, type_name: str):
        """Set operation type and move to next state."""
        context = self.get_context(user_id)
        context.type = type_name
        self.set_state(user_id, State.INPUT_DESCRIPTION)
    
    def set_description(self, user_id: int, description: str):
        """Set operation description and move to confirm state."""
        context = self.get_context(user_id)
        context.description = description
        self.set_state(user_id, State.CONFIRM)
    
    def skip_description(self, user_id: int):
        """Skip description and move to confirm state."""
        context = self.get_context(user_id)
        context.description = ""
        self.set_state(user_id, State.CONFIRM)
    
    def confirm(self, user_id: int):
        """Move to save state."""
        self.set_state(user_id, State.SAVE)
    
    def get_operation_data(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get operation data from context."""
        context = self.get_context(user_id)
        
        # Required fields for saving an operation
        if not all([
            context.direction,
            context.date,
            context.amount is not None,
        ]):
            return None

        # Category/type can be optional.
        # For rental operations we can auto-fill category/type if missing.
        is_rental = bool(context.rental_address and context.rental_mm)
        if is_rental:
            category = context.category or "Доходы от аренды"
            # If type is not set (None) or explicitly empty, we still provide something stable
            type_name = context.type if (context.type is not None and context.type != "") else f"{context.rental_address} {context.rental_mm}"
        else:
            category = context.category or ""
            type_name = context.type if context.type is not None else ""
        
        result = {
            "date": context.date,
            "direction": context.direction,
            "amount": context.amount,
            "category": category,
            "type": type_name,
            "description": context.description or "",
        }
        
        # Add rental fields if present
        if context.rental_address:
            result["address"] = context.rental_address
        if context.rental_mm:
            result["mm_number"] = context.rental_mm
        
        return result
    
    def is_in_operation_flow(self, user_id: int) -> bool:
        """Check if user is in operation flow (not IDLE)."""
        state = self.get_state(user_id)
        return state != State.IDLE
    
    def can_cancel(self, user_id: int) -> bool:
        """Check if current state allows cancellation."""
        return self.is_in_operation_flow(user_id)
    
    def go_back(self, user_id: int) -> bool:
        """
        Go back to previous state.
        Returns True if went back, False if already at first state.
        """
        state = self.get_state(user_id)
        context = self.get_context(user_id)
        
        if state == State.SELECT_OPERATION_TYPE:
            # Can't go back from first state
            return False
        elif state == State.SELECT_DATE:
            # Go back to operation type selection
            context.direction = None
            self.set_state(user_id, State.SELECT_OPERATION_TYPE)
            return True
        elif state == State.INPUT_AMOUNT:
            # Go back to date selection
            context.date = None
            self.set_state(user_id, State.SELECT_DATE)
            return True
        elif state == State.SELECT_CATEGORY:
            # Go back to amount input
            context.amount = None
            self.set_state(user_id, State.INPUT_AMOUNT)
            return True
        elif state == State.SELECT_TYPE:
            # Go back to category selection
            context.category = None
            self.set_state(user_id, State.SELECT_CATEGORY)
            return True
        elif state == State.INPUT_DESCRIPTION:
            # Go back to type selection
            context.type = None
            self.set_state(user_id, State.SELECT_TYPE)
            return True
        elif state == State.CONFIRM:
            # Go back to description input
            context.description = None
            self.set_state(user_id, State.INPUT_DESCRIPTION)
            return True
        elif state == State.SELECT_RENTAL_ADDRESS:
            # Go back to category selection
            context.category = None
            self.set_state(user_id, State.SELECT_CATEGORY)
            return True
        elif state == State.SELECT_RENTAL_MM:
            # Go back to address selection
            context.rental_address = None
            self.set_state(user_id, State.SELECT_RENTAL_ADDRESS)
            return True
        elif state == State.INPUT_RENTAL_AMOUNT:
            # Go back to М/М selection
            context.rental_mm = None
            self.set_state(user_id, State.SELECT_RENTAL_MM)
            return True
        else:
            return False
    
    def set_rental_address(self, user_id: int, address: str):
        """Set rental address and move to М/М selection."""
        context = self.get_context(user_id)
        context.rental_address = address
        self.set_state(user_id, State.SELECT_RENTAL_MM)
    
    def set_rental_mm(self, user_id: int, mm_number: str):
        """Set rental М/М and move to description or confirm."""
        context = self.get_context(user_id)
        context.rental_mm = mm_number
        # If this is a rental payment flow (not through category), go to amount input
        # Otherwise go to description
        if context.category == "Доходы от аренды":
            self.set_state(user_id, State.INPUT_DESCRIPTION)
        else:
            self.set_state(user_id, State.INPUT_RENTAL_AMOUNT)
    
    def set_rental_amount(self, user_id: int, amount: float):
        """Set rental payment amount and move to confirm."""
        context = self.get_context(user_id)
        context.amount = amount
        self.set_state(user_id, State.CONFIRM)


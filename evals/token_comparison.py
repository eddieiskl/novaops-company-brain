from __future__ import annotations


LESSON10_STAGE3_FINAL_TURN_INPUT_TOKENS = 62864
MAYA_DETERMINISTIC_FINAL_TURN_MODEL_INPUT_TOKENS = 0


def main() -> None:
    saved = LESSON10_STAGE3_FINAL_TURN_INPUT_TOKENS - MAYA_DETERMINISTIC_FINAL_TURN_MODEL_INPUT_TOKENS
    print("final_turn_input_tokens")
    print(f"lesson10_stage3={LESSON10_STAGE3_FINAL_TURN_INPUT_TOKENS}")
    print(f"maya_deterministic={MAYA_DETERMINISTIC_FINAL_TURN_MODEL_INPUT_TOKENS}")
    print(f"delta={-saved}")
    print("note=Maya currently produces deterministic structured answers without an answering-model call.")


if __name__ == "__main__":
    main()

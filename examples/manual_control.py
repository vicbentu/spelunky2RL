"""
Manual Control Example

This script demonstrates how to use manual keyboard control to test the SpelunkyRL environment.
Useful for:
- Testing your installation
- Debugging environment behavior
- Understanding game mechanics
- Playing Spelunky 2 with god mode

Controls:
- Arrow keys: Movement
- Z: Jump
- X: Whip/Attack
- C: Bomb
- V: Rope
- Shift: Run
- Up Arrow (at door): Enter door

Press Ctrl+C to exit.
"""

from spelunky2rl.envs.dummy_environment import SpelunkyEnv

if __name__ == "__main__":
    print("=" * 60)
    print("SpelunkyRL Manual Control Example")
    print("=" * 60)
    print("\nInitializing environment with manual control enabled...")
    print("This may take a few seconds...\n")

    env = SpelunkyEnv(
        # TODO: Update these paths to match your installation
        spelunky_dir=r"C:\Path\To\Spelunky 2",
        playlunky_dir=r"C:\Path\To\playlunky\nightly",

        # Environment settings
        frames_per_step=6,      # How many game frames per step
        speedup=False,          # Don't speed up the game
        manual_control=True,    # ENABLE MANUAL CONTROL
        god_mode=True,          # Invulnerability for testing
        render_enabled=False,   # Don't capture frames (saves performance)
        console=True            # Show console for debugging
    )

    print("Environment initialized successfully!")
    print("\nStarting game...")
    print("You can now control the character with your keyboard.")
    print("Press Ctrl+C in this terminal to exit.\n")
    print("=" * 60)

    try:
        # Reset the environment
        obs, _ = env.reset()

        # Run forever (or until Ctrl+C)
        step_count = 0
        while True:
            # The environment is in manual control mode,
            # so the action we pass doesn't matter (player controls with keyboard)
            action = env.action_space.sample()

            obs, reward, done, truncated, info = env.step(action)
            step_count += 1

            # Reset if episode ends (though in god mode this rarely happens)
            if done or truncated:
                print(f"Episode ended after {step_count} steps. Resetting...")
                obs, _ = env.reset()
                step_count = 0

    except KeyboardInterrupt:
        print("\n\nExiting gracefully...")

    finally:
        env.close()
        print("Environment closed. Goodbye!")

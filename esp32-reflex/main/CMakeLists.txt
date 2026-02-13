idf_component_register(
    SRCS "app_main.cpp"
         "motor.cpp"
         "encoder.cpp"
         "imu.cpp"
         "protocol.cpp"
         "config.cpp"
         "usb_rx.cpp"
         "telemetry.cpp"
         "control.cpp"
         "safety.cpp"
         "range_ultrasonic.cpp"
    INCLUDE_DIRS "."
)

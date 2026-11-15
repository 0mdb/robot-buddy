# Pi link transport (Kconfig.projbuild): USB CDC for the bench, P2 UART in the robot.
if(CONFIG_FACE_TRANSPORT_UART)
    set(link_src "uart_link.cpp")
else()
    set(link_src "usb_composite.cpp")
endif()

idf_component_register(
    SRCS "app_main.cpp"
         "protocol.cpp"
         "${link_src}"
         "usb_rx.cpp"
         "telemetry.cpp"
         "display.cpp"
         "touch.cpp"
         "face_state.cpp"
         "system_face.cpp"
         "face_ui.cpp"
         "conv_border.cpp"
         "touch_gesture.cpp"
         "led.cpp"
    INCLUDE_DIRS "."
    REQUIRES "esp_lcd" "esp_timer" "driver" "esp_system"
)

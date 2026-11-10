#pragma once
#include "FreeRTOS.h"
inline TickType_t xTaskGetTickCount()
{
    return 0;
}
inline BaseType_t xTaskDelayUntil(TickType_t*, TickType_t)
{
    return pdTRUE;
}

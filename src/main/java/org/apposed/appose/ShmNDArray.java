/*-
 * #%L
 * Appose: multi-language interprocess plugins with shared memory ndarrays.
 * %%
 * Copyright (C) 2023 Appose developers.
 * %%
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 * 
 * 1. Redistributions of source code must retain the above copyright notice,
 *    this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright notice,
 *    this list of conditions and the following disclaimer in the documentation
 *    and/or other materials provided with the distribution.
 * 
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
 * ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDERS OR CONTRIBUTORS BE
 * LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
 * CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
 * SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
 * CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 * ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 * #L%
 */

package org.apposed.appose;

/**
 * Implementation of {@link NDArray} backed by {@link SharedMemory}.
 *
 * @param <T> The type of each array element.
 */
public abstract class ShmNDArray<T> implements NDArray<T> {
	
	// Mark really wants this to be called ShmagePlus! :-P

	/**
	 * TODO
	 * 
	 * @param shape tuple of ints : Shape of created array.
	 * @param dtype data-type, optional : Any object that can be interpreted as a
	 *          numpy data type.
	 * @param buffer object exposing buffer interface, optional : Used to fill the
	 *          array with data.
	 * @param offset int, optional : Offset of array data in buffer.
	 * @param strides tuple of ints, optional : Strides of data in memory.
	 * @param cOrder {'C', 'F'}, optional : If true, row-major (C-style) order; if
	 *          false, column-major (Fortran-style) order.
	 */
	public ShmNDArray(long[] shape, Class<T> dtype, SharedMemory buffer,
		long offset, long[] strides, boolean cOrder)
	{
		
	}
}